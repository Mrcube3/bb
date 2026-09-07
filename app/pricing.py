from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .models import Freshness, PriceRecord, PricingInput


class PricingEngine:
    """Deterministic, bounded pricing. The LLM can never set prices."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def price(self, inp: PricingInput) -> PriceRecord:
        now = datetime.now(timezone.utc)
        base = self.settings.base_price
        multipliers: dict[str, float] = {}

        if inp.freshness == Freshness.STALE or inp.freshness == Freshness.EXPIRED:
            multipliers["freshness"] = 0.8

        asset_mult = self._accuracy_multiplier(inp.resolved_count_by_asset, inp.accuracy_by_asset)
        if asset_mult is not None:
            multipliers["asset_quality"] = asset_mult

        horizon_mult = self._accuracy_multiplier(inp.resolved_count_by_horizon, inp.accuracy_by_horizon)
        if horizon_mult is not None:
            multipliers["horizon_quality"] = horizon_mult

        if inp.demand > 0:
            multipliers["demand"] = min(1.5, 1.0 + inp.demand * 0.02)

        final = base
        for mult in multipliers.values():
            final *= mult
        final = max(self.settings.min_price, min(self.settings.max_price, final))

        classification = "BASE_PRICE_INSUFFICIENT_HISTORY"
        if inp.resolved_count_by_asset >= self.settings.min_reputation_sample or inp.resolved_count_by_horizon >= self.settings.min_reputation_sample:
            classification = "REPUTATION_BASED"

        return PriceRecord(
            base_price=base,
            multipliers=multipliers,
            formula_version=self.settings.pricing_version,
            final_price=final,
            timestamp=now,
            min_price=self.settings.min_price,
            max_price=self.settings.max_price,
            classification=classification,
        )

    @staticmethod
    def _accuracy_multiplier(n: int, accuracy: float | None) -> float | None:
        if accuracy is None or n < 20:
            return None
        if accuracy >= 0.75:
            return 1.5
        if accuracy >= 0.65:
            return 1.25
        if accuracy >= 0.55:
            return 1.0
        if accuracy >= 0.45:
            return 0.85
        return 0.7