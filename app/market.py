from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .config import Settings
from .models import Classification, Evidence, Freshness


class ProviderError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BinanceSpotMarket:
    """Public Binance Spot market adapter. No account or trading authority is used."""

    name = "binance_spot_public_market"

    def __init__(self, settings: Settings):
        self.settings = settings

    def _get(self, path: str, query: dict[str, Any]) -> Any:
        url = self.settings.binance_base_url.rstrip("/") + path + "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "prometheus/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ProviderError(f"Binance market request failed: {type(exc).__name__}: {exc}") from exc

    def ping(self) -> None:
        self._get("/api/v3/ping", {})

    def snapshot(self, asset: str, limit: int = 120) -> dict[str, Any]:
        retrieved = _now()
        ticker = self._get("/api/v3/ticker/bookTicker", {"symbol": asset})
        candles = self._get("/api/v3/klines", {"symbol": asset, "interval": "1m", "limit": limit})
        if not ticker or not candles:
            raise ProviderError("Binance returned no market data")
        bid = Decimal(str(ticker["bidPrice"]))
        ask = Decimal(str(ticker["askPrice"]))
        mid = (bid + ask) / Decimal("2")
        server_time = self._server_time()
        age_ms = int((time.time() * 1000) - server_time) if server_time else 0
        freshness = Freshness.FRESH if age_ms <= 30_000 else Freshness.AGING if age_ms <= 120_000 else Freshness.STALE
        return {
            "asset": asset,
            "venue": "BINANCE_SPOT",
            "bid": float(bid),
            "ask": float(ask),
            "mid": float(mid),
            "server_data": {"bidPrice": ticker["bidPrice"], "askPrice": ticker["askPrice"]},
            "server_time_ms": server_time,
            "candles": candles,
            "source": self.settings.binance_base_url,
            "retrieved_at": retrieved.isoformat(),
            "timestamp": retrieved.isoformat(),
            "age_ms": max(0, age_ms),
            "freshness": freshness.value,
            "classification": Classification.BINANCE_REPORTED.value,
        }

    def _server_time(self) -> int | None:
        try:
            data = self._get("/api/v3/time", {})
            return int(data["serverTime"])
        except (ProviderError, KeyError, TypeError):
            return None

    def price_at_or_after(self, asset: str, timestamp_ms: int) -> dict[str, Any]:
        candles = self._get("/api/v3/klines", {"symbol": asset, "interval": "1m", "startTime": timestamp_ms, "limit": 1})
        if not candles:
            raise ProviderError("Binance returned no resolution candle")
        candle = candles[0]
        return {"price": float(candle[4]), "open_time_ms": int(candle[0]), "source": self.settings.binance_base_url}

    def order_book_imbalance(self, asset: str, limit: int = 50) -> dict[str, Any]:
        data = self._get("/api/v3/depth", {"symbol": asset, "limit": limit})
        bids = [(float(p), float(q)) for p, q in data.get("bids", [])]
        asks = [(float(p), float(q)) for p, q in data.get("asks", [])]
        bid_vol = sum(q for _, q in bids)
        ask_vol = sum(q for _, q in asks)
        total = bid_vol + ask_vol
        imbalance = (bid_vol - ask_vol) / total if total > 0 else 0.0
        return {
            "bid_volume": bid_vol,
            "ask_volume": ask_vol,
            "imbalance": imbalance,
            "bid_depth_count": len(bids),
            "ask_depth_count": len(asks),
            "source": self.settings.binance_base_url,
            "retrieved_at": _now().isoformat(),
        }


def evidence(key: str, value: Any, source: str, timestamp: datetime, classification: Classification, age_ms: int = 0) -> Evidence:
    freshness = Freshness.FRESH if age_ms <= 30_000 else Freshness.AGING if age_ms <= 120_000 else Freshness.STALE
    return Evidence(
        key=key,
        value=value,
        source=source,
        timestamp=timestamp,
        retrieved_at=_now(),
        age_ms=age_ms,
        freshness=freshness,
        classification=classification,
    )