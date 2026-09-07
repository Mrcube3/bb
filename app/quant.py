from __future__ import annotations

import math
import statistics
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .market import BinanceSpotMarket, evidence
from .models import Classification, QuantPacket


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _ema(values: list[float], period: int) -> float:
    alpha = 2 / (period + 1)
    current = values[0]
    for value in values[1:]:
        current = alpha * value + (1 - alpha) * current
    return current


def _rsi(values: list[float], period: int = 14) -> float:
    if len(values) < period + 1:
        return 50.0
    changes = [values[i] - values[i - 1] for i in range(1, period + 1)]
    gains = [c for c in changes if c > 0]
    losses = [-c for c in changes if c < 0]
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def build_quant_packet(snapshot: dict[str, Any], market: BinanceSpotMarket | None = None, settings: Settings | None = None) -> QuantPacket:
    assets = snapshot.get("order_book", {})
    candles = snapshot["candles"]
    closes = [float(c[4]) for c in candles]
    highs = [float(c[2]) for c in candles]
    lows = [float(c[3]) for c in candles]
    volumes = [float(c[5]) for c in candles]
    if len(closes) < 30:
        raise ValueError("at least 30 Binance 1m candles are required")
    now = datetime.fromisoformat(snapshot["retrieved_at"])
    prior_15m = closes[-16]
    current = closes[-1]
    returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    recent_returns = returns[-20:]
    volatility = statistics.pstdev(recent_returns) * math.sqrt(60) if len(recent_returns) > 1 else 0.0
    range_values = [highs[i] - lows[i] for i in range(max(0, len(closes) - 14), len(closes))]
    atr_14 = _mean(range_values)
    ema_fast = _ema(closes[-30:], 9)
    ema_slow = _ema(closes[-30:], 21)
    volume_change = (volumes[-1] / _mean(volumes[-11:-1])) - 1 if _mean(volumes[-11:-1]) else 0.0
    spread_bps = ((snapshot["ask"] - snapshot["bid"]) / snapshot["mid"]) * 10_000 if snapshot["mid"] else 0.0
    rsi_14 = _rsi(closes[-30:], 14)
    order_book_imbalance = assets.get("imbalance") if assets else None

    features = {
        "current_price": current,
        "bid": snapshot["bid"],
        "ask": snapshot["ask"],
        "mid": snapshot["mid"],
        "spread_bps": spread_bps,
        "return_15m": (current - prior_15m) / prior_15m,
        "realized_volatility_20m": volatility,
        "atr_14": atr_14,
        "ema_fast_9": ema_fast,
        "ema_slow_21": ema_slow,
        "ema_fast_above_slow": ema_fast > ema_slow,
        "rsi_14": rsi_14,
        "volume_change_10m": volume_change,
        "candle_count": len(closes),
    }
    if order_book_imbalance is not None:
        features["order_book_imbalance"] = order_book_imbalance

    source = snapshot["source"]
    ts = now
    ev = {
        "current_price": evidence("current_price", current, source, ts, Classification.BINANCE_REPORTED),
        "bid": evidence("bid", snapshot["bid"], source, ts, Classification.BINANCE_REPORTED),
        "ask": evidence("ask", snapshot["ask"], source, ts, Classification.BINANCE_REPORTED),
        "mid": evidence("mid", snapshot["mid"], source, ts, Classification.BINANCE_REPORTED),
        "return_15m": evidence("return_15m", features["return_15m"], "PROMETHEUS:quant-v1", ts, Classification.PROMETHEUS_ESTIMATE),
        "realized_volatility_20m": evidence("realized_volatility_20m", volatility, "PROMETHEUS:quant-v1", ts, Classification.PROMETHEUS_ESTIMATE),
        "atr_14": evidence("atr_14", atr_14, "PROMETHEUS:quant-v1", ts, Classification.PROMETHEUS_ESTIMATE),
        "ema_fast_9": evidence("ema_fast_9", ema_fast, "PROMETHEUS:quant-v1", ts, Classification.PROMETHEUS_ESTIMATE),
        "ema_slow_21": evidence("ema_slow_21", ema_slow, "PROMETHEUS:quant-v1", ts, Classification.PROMETHEUS_ESTIMATE),
        "rsi_14": evidence("rsi_14", rsi_14, "PROMETHEUS:quant-v1", ts, Classification.PROMETHEUS_ESTIMATE),
        "volume_change_10m": evidence("volume_change_10m", volume_change, "PROMETHEUS:quant-v1", ts, Classification.PROMETHEUS_ESTIMATE),
    }
    if order_book_imbalance is not None:
        ev["order_book_imbalance"] = evidence("order_book_imbalance", order_book_imbalance, source, ts, Classification.BINANCE_REPORTED)

    formula_version = settings.quant_formula_version if settings else "quant-v1"

    return QuantPacket(
        packet_id=str(uuid.uuid4()), asset=snapshot["asset"], venue="BINANCE_SPOT", generated_at=ts,
        formula_version=formula_version, snapshot=snapshot, features=features, evidence=ev,
    )