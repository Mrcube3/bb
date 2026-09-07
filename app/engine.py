from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .canonical import sha256_json
from .config import Settings, HORIZON_SECONDS
from .db import Database
from .evidence import EvidenceValidator
from .market import BinanceSpotMarket, ProviderError
from .models import Direction, Preview, PricingInput, QuantPacket, Signal, SignalState
from .pricing import PricingEngine
from .quant import build_quant_packet


VALID_TRANSITIONS: dict[SignalState, set[SignalState]] = {
    SignalState.DRAFT: {SignalState.VALIDATING},
    SignalState.VALIDATING: {SignalState.REJECTED, SignalState.FROZEN},
    SignalState.FROZEN: {SignalState.LISTED},
    SignalState.LISTED: {SignalState.PURCHASED, SignalState.EXPIRED, SignalState.AWAITING_OUTCOME},
    SignalState.PURCHASED: {SignalState.DELIVERED},
    SignalState.DELIVERED: {SignalState.AWAITING_OUTCOME},
    SignalState.AWAITING_OUTCOME: {SignalState.MATURED, SignalState.UNRESOLVED},
    SignalState.MATURED: {SignalState.SCORED},
    SignalState.SCORED: {SignalState.VERIFIED},
}


class SignalEngine:
    def __init__(self, db: Database, market: BinanceSpotMarket, settings: Settings, pricing: PricingEngine | None = None, validator: EvidenceValidator | None = None):
        self.db = db
        self.market = market
        self.settings = settings
        self.validator = validator or EvidenceValidator()
        self.pricing = pricing or PricingEngine(settings)

    def _price(self, quant: QuantPacket) -> float:
        return float(quant.features["current_price"])

    def create(self, asset: str, horizon: str | None = None, ob_data: dict[str, Any] | None = None) -> Signal:
        asset = asset.upper()
        horizon = (horizon or self.settings.default_horizon).upper()
        if asset not in self.settings.assets:
            raise ValueError(f"unsupported asset: {asset}")
        if horizon not in HORIZON_SECONDS:
            raise ValueError(f"unsupported horizon: {horizon}")
        snapshot = self.market.snapshot(asset)
        if ob_data:
            snapshot["order_book"] = ob_data
        quant = build_quant_packet(snapshot, self.market, self.settings)
        signal_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        price = self._price(quant)
        ret = float(quant.features["return_15m"])
        ema_fast = bool(quant.features["ema_fast_above_slow"])
        vol = float(quant.features["realized_volatility_20m"])
        rsi = float(quant.features.get("rsi_14", 50.0))

        if ret > 0.0005 and ema_fast and rsi < 70:
            direction = Direction.LONG
            thesis = "15m momentum is positive, the fast EMA is above the slow EMA, and RSI is not overbought."
            evidence_keys = ["return_15m", "ema_fast_9", "ema_slow_21", "rsi_14", "realized_volatility_20m", "current_price"]
            invalidation = price * (1 - max(0.001, min(0.02, vol * 1.5)))
        elif ret < -0.0005 and not ema_fast and rsi > 30:
            direction = Direction.SHORT
            thesis = "15m momentum is negative, the fast EMA is below the slow EMA, and RSI is not oversold."
            evidence_keys = ["return_15m", "ema_fast_9", "ema_slow_21", "rsi_14", "realized_volatility_20m", "current_price"]
            invalidation = price * (1 + max(0.001, min(0.02, vol * 1.5)))
        else:
            direction = Direction.NEUTRAL
            thesis = "Momentum and moving-average evidence do not align strongly enough for a directional signal."
            evidence_keys = ["return_15m", "ema_fast_9", "ema_slow_21", "current_price"]
            invalidation = price

        confidence = min(0.95, max(0.05, 0.5 + min(0.35, abs(ret) * 12) + (0.05 if (ema_fast == (direction == Direction.LONG)) else 0)))
        signal = Signal(
            signal_id=signal_id, created_at=now, asset=asset, venue="BINANCE_SPOT", direction=direction,
            horizon=horizon.lower(), horizon_seconds=HORIZON_SECONDS[horizon], confidence=confidence,
            model_provider=self.settings.model_provider, model_version=self.settings.model_version,
            prompt_schema_version=self.settings.prompt_schema_version, entry_reference=price, invalidation=invalidation,
            evidence_keys=evidence_keys,
            thesis=thesis, risk_factors=["Short-horizon market noise can invalidate the thesis.", "Spread and execution costs are not included in the return calculation."],
            snapshot_reference=quant.packet_id, state=SignalState.DRAFT,
        )
        self.db.journal("SIGNAL_CREATED", signal.signal_id, {"asset": asset, "direction": direction.value, "horizon": horizon}, now.isoformat())
        self._validate_and_freeze(signal, snapshot, quant)
        return signal

    def _validate_and_freeze(self, signal: Signal, snapshot: dict[str, Any], quant: QuantPacket) -> None:
        existing = self.db.fetchone("SELECT signal_id FROM signals WHERE signal_id=?", (signal.signal_id,))
        if existing:
            self._transition(signal.signal_id, SignalState.VALIDATING)
        self.validator.validate(signal, quant)
        snapshot_hash = sha256_json(snapshot)
        quant_hash = sha256_json(quant.model_dump(mode="json"))
        immutable = signal.model_dump(mode="json", exclude={"state", "published_at"})
        signal_hash = sha256_json(immutable)
        now = datetime.now(timezone.utc)
        price_record = self.pricing.price(
            PricingInput(
                asset=signal.asset, horizon=signal.horizon,
            )
        )
        listed_price = price_record.final_price
        passport = {
            "signal": signal.model_dump(mode="json"), "snapshot": snapshot, "quant_packet": quant.model_dump(mode="json"),
            "snapshot_hash": snapshot_hash, "quant_hash": quant_hash, "signal_hash": signal_hash,
            "pricing": price_record.model_dump(mode="json"),
            "listed_price": listed_price, "currency": self.settings.currency,
            "environment": self.settings.environment, "verification_status": "FROZEN",
        }
        preview = Preview(signal_id=signal.signal_id, asset=signal.asset, horizon=signal.horizon, created_at=signal.created_at,
                          listed_price=listed_price, currency=self.settings.currency, model_provider=signal.model_provider,
                          model_version=signal.model_version, freshness="FRESH", reputation={"status": "INSUFFICIENT_SAMPLE"}, state=SignalState.LISTED,
                          outcome_due_at=now + timedelta(seconds=signal.horizon_seconds))
        published = signal.model_copy(update={"published_at": now, "state": SignalState.LISTED})
        due = published.published_at + timedelta(seconds=published.horizon_seconds)
        self.db.execute(
            "INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (signal.signal_id, published.state.value, published.created_at.isoformat(), published.published_at.isoformat(), published.asset,
             published.horizon, published.horizon_seconds, listed_price, self.settings.currency, preview.model_dump_json(),
             json.dumps(passport, sort_keys=True), published.model_dump_json(), snapshot_hash, quant_hash, signal_hash, due.isoformat()),
        )
        self.db.event("SIGNAL_FROZEN", signal.signal_id, {"signal_hash": signal_hash, "snapshot_hash": snapshot_hash, "quant_hash": quant_hash}, now.isoformat())
        self.db.journal("SIGNAL_FROZEN", signal.signal_id, {"signal_hash": signal_hash, "snapshot_hash": snapshot_hash, "listed_price": listed_price}, now.isoformat())

    def _transition(self, signal_id: str, target: SignalState) -> None:
        row = self.db.fetchone("SELECT state FROM signals WHERE signal_id=?", (signal_id,))
        if not row:
            raise ValueError("signal not found")
        current = SignalState(row["state"])
        if target not in VALID_TRANSITIONS.get(current, set()):
            raise ValueError(f"invalid signal transition {current.value} -> {target.value}")
        self.db.execute("UPDATE signals SET state=? WHERE signal_id=?", (target.value, signal_id))

    def list_previews(self) -> list[dict[str, Any]]:
        return [json.loads(row["preview_json"]) for row in self.db.fetchall(
            "SELECT preview_json FROM signals WHERE state IN ('LISTED','PURCHASED','DELIVERED','AWAITING_OUTCOME') ORDER BY created_at DESC"
        )]

    def get(self, signal_id: str) -> dict[str, Any] | None:
        row = self.db.fetchone("SELECT * FROM signals WHERE signal_id=?", (signal_id,))
        return dict(row) if row else None