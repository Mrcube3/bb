from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _csv(name: str, default: str) -> tuple[str, ...]:
    value = os.getenv(name, default)
    return tuple(item.strip().upper() for item in value.split(",") if item.strip())


HORIZON_SECONDS = {"10M": 600, "15M": 900, "1H": 3600, "4H": 14400, "24H": 86400}


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("PROMETHEUS_DB_PATH", "./prometheus.db")
    assets: tuple[str, ...] = _csv("PROMETHEUS_ASSETS", "BTCUSDT,ETHUSDT,SOLUSDT")
    horizons: tuple[str, ...] = _csv("PROMETHEUS_HORIZONS", "10M,15M,1H,4H,24H")
    default_horizon: str = os.getenv("PROMETHEUS_DEFAULT_HORIZON", "10m").lower()
    list_interval_seconds: int = int(os.getenv("PROMETHEUS_LIST_INTERVAL_SECONDS", "60"))
    min_reputation_sample: int = int(os.getenv("PROMETHEUS_MIN_REPUTATION_SAMPLE", "20"))
    base_price: float = float(os.getenv("PROMETHEUS_BASE_PRICE", "0.01"))
    min_price: float = float(os.getenv("PROMETHEUS_MIN_PRICE", "0.005"))
    max_price: float = float(os.getenv("PROMETHEUS_MAX_PRICE", "0.05"))
    currency: str = os.getenv("PROMETHEUS_CURRENCY", "USDC")
    environment: str = os.getenv("PROMETHEUS_ENVIRONMENT", "local")
    binance_base_url: str = os.getenv("PROMETHEUS_BINANCE_BASE_URL", "https://data-api.binance.vision")
    facilitator_url: str = os.getenv("PROMETHEUS_FACILITATOR_URL", "").rstrip("/")
    x402_network: str = os.getenv("PROMETHEUS_X402_NETWORK", "")
    x402_asset: str = os.getenv("PROMETHEUS_X402_ASSET", "USDC")
    x402_pay_to: str = os.getenv("PROMETHEUS_X402_PAY_TO", "")
    x402_scheme: str = os.getenv("PROMETHEUS_X402_SCHEME", "exact")
    enable_scheduler: bool = os.getenv("PROMETHEUS_ENABLE_SCHEDULER", "true").lower() == "true"
    model_provider: str = os.getenv("PROMETHEUS_MODEL_PROVIDER", "PROMETHEUS_DETERMINISTIC")
    model_version: str = os.getenv("PROMETHEUS_MODEL_VERSION", "signal-v1")
    prompt_schema_version: str = os.getenv("PROMETHEUS_PROMPT_SCHEMA_VERSION", "prompt-v1")
    quant_formula_version: str = os.getenv("PROMETHEUS_QUANT_FORMULA_VERSION", "quant-v1")
    outcome_method_version: str = os.getenv("PROMETHEUS_OUTCOME_METHOD_VERSION", "outcome-v1")
    pricing_version: str = os.getenv("PROMETHEUS_PRICING_VERSION", "price-v1")

    @property
    def db_file(self) -> Path:
        return Path(self.db_path).expanduser()

    @property
    def payments_configured(self) -> bool:
        return bool(self.facilitator_url and self.x402_network and self.x402_pay_to)

    @property
    def horizon_seconds(self) -> dict[str, int]:
        return {h.upper(): HORIZON_SECONDS.get(h.upper(), 600) for h in self.horizons}


settings = Settings()
