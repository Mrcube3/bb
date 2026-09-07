from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from .config import Settings
from .db import Database
from .market import BinanceSpotMarket, ProviderError
from .models import Direction, Outcome, SignalState


class OutcomeResolver:
    def __init__(self, db: Database, market: BinanceSpotMarket, settings: Settings):
        self.db = db
        self.market = market
        self.settings = settings

    def resolve_due(self) -> list[dict]:
        now_iso = datetime.now(timezone.utc).isoformat()
        rows = self.db.fetchall(
            "SELECT * FROM signals WHERE state IN ('LISTED','DELIVERED','AWAITING_OUTCOME') AND outcome_due_at <= ?",
            (now_iso,),
        )
        resolved = []
        for row in rows:
            try:
                self.db.execute("UPDATE signals SET state=? WHERE signal_id=?", (SignalState.AWAITING_OUTCOME.value, row["signal_id"]))
                outcome = self._resolve(row)
                resolved.append(outcome.model_dump(mode="json"))
                self.db.journal("OUTCOME_RESOLVED", row["signal_id"], {"directional_result": outcome.directional_result, "raw_return": outcome.raw_return}, now_iso)
            except ProviderError as exc:
                self.db.execute("UPDATE signals SET state=? WHERE signal_id=?", (SignalState.UNRESOLVED.value, row["signal_id"]))
                self.db.event("OUTCOME_UNRESOLVED", row["signal_id"], {"reason": str(exc)}, now_iso)
                self.db.journal("OUTCOME_UNRESOLVED", row["signal_id"], {"reason": str(exc)}, now_iso)
        return resolved

    def _resolve(self, row: sqlite3.Row) -> Outcome:
        existing = self.db.fetchone("SELECT outcome_json FROM outcomes WHERE signal_id=?", (row["signal_id"],))
        if existing:
            return Outcome.model_validate_json(existing["outcome_json"])
        signal = json.loads(row["signal_json"])
        due_ms = int(datetime.fromisoformat(row["outcome_due_at"]).timestamp() * 1000)
        result = self.market.price_at_or_after(row["asset"], due_ms)
        entry = float(signal["entry_reference"])
        exit_price = float(result["price"])
        direction = Direction(signal["direction"])
        if direction == Direction.LONG:
            raw = (exit_price - entry) / entry
            verdict = "CORRECT" if raw > 0 else "INCORRECT" if raw < 0 else "NEUTRAL"
        elif direction == Direction.SHORT:
            raw = (entry - exit_price) / entry
            verdict = "CORRECT" if raw > 0 else "INCORRECT" if raw < 0 else "NEUTRAL"
        else:
            raw = 0.0
            verdict = "NEUTRAL"
        now_iso = datetime.now(timezone.utc).isoformat()
        outcome = Outcome(
            outcome_id=str(uuid.uuid4()), signal_id=row["signal_id"], resolved_at=datetime.now(timezone.utc),
            entry_reference=entry, resolution_price=exit_price, raw_return=raw, directional_result=verdict,
            source=result["source"], provenance={"resolution_candle_open_time_ms": result["open_time_ms"]},
            methodology_version=self.settings.outcome_method_version,
        )
        self.db.execute(
            "INSERT INTO outcomes(outcome_id, signal_id, outcome_json, created_at) VALUES (?, ?, ?, ?)",
            (outcome.outcome_id, row["signal_id"], outcome.model_dump_json(), now_iso),
        )
        self.db.execute("UPDATE signals SET state=? WHERE signal_id=?", (SignalState.VERIFIED.value, row["signal_id"]))
        self.db.event("OUTCOME_VERIFIED", row["signal_id"], outcome.model_dump(mode="json"), now_iso)
        return outcome