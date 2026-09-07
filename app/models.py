from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Classification(str, Enum):
    BINANCE_REPORTED = "BINANCE_REPORTED"
    PROMETHEUS_ESTIMATE = "PROMETHEUS_ESTIMATE"
    SIMULATION = "SIMULATION"
    UNAVAILABLE = "UNAVAILABLE"


class Freshness(str, Enum):
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    UNAVAILABLE = "UNAVAILABLE"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
    STAND_DOWN = "STAND_DOWN"


class SignalState(str, Enum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    REJECTED = "REJECTED"
    FROZEN = "FROZEN"
    LISTED = "LISTED"
    PURCHASED = "PURCHASED"
    DELIVERED = "DELIVERED"
    AWAITING_OUTCOME = "AWAITING_OUTCOME"
    MATURED = "MATURED"
    SCORED = "SCORED"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    UNRESOLVED = "UNRESOLVED"


class PaymentState(str, Enum):
    CREATED = "CREATED"
    PAYMENT_REQUIRED = "PAYMENT_REQUIRED"
    PAYMENT_SUBMITTED = "PAYMENT_SUBMITTED"
    VERIFYING = "VERIFYING"
    PAID = "PAID"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"
    REFUNDED = "REFUNDED"


class VerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"


class Signal(BaseModel):
    signal_id: str
    created_at: datetime
    published_at: datetime | None = None
    asset: str
    venue: Literal["BINANCE_SPOT"]
    direction: Direction
    horizon: str
    horizon_seconds: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    model_provider: str
    model_version: str
    prompt_schema_version: str
    entry_reference: float = Field(gt=0)
    invalidation: float = Field(gt=0)
    evidence_keys: list[str] = Field(min_length=1)
    thesis: str = Field(min_length=1)
    risk_factors: list[str] = Field(min_length=1)
    snapshot_reference: str
    state: SignalState = SignalState.DRAFT

    @field_validator("asset")
    @classmethod
    def uppercase_asset(cls, value: str) -> str:
        return value.upper()


class Evidence(BaseModel):
    key: str
    value: Any
    source: str
    timestamp: datetime
    retrieved_at: datetime
    age_ms: int = Field(ge=0)
    freshness: Freshness
    classification: Classification


class QuantPacket(BaseModel):
    packet_id: str
    asset: str
    venue: Literal["BINANCE_SPOT"]
    generated_at: datetime
    formula_version: str
    snapshot: dict[str, Any]
    features: dict[str, Any]
    evidence: dict[str, Evidence]
    classification: Classification = Classification.PROMETHEUS_ESTIMATE


class Preview(BaseModel):
    signal_id: str
    asset: str
    horizon: str
    created_at: datetime
    listed_price: float
    currency: str
    model_provider: str
    model_version: str
    freshness: Freshness
    reputation: dict[str, Any]
    state: SignalState
    outcome_due_at: datetime | None = None


class Outcome(BaseModel):
    outcome_id: str
    signal_id: str
    resolved_at: datetime
    entry_reference: float
    resolution_price: float
    raw_return: float
    directional_result: Literal["CORRECT", "INCORRECT", "NEUTRAL", "UNRESOLVED"]
    source: str
    provenance: dict[str, Any]
    methodology_version: str


class PaymentRequirement(BaseModel):
    x402Version: int = 1
    accepts: list[dict[str, Any]]


class ProviderStatus(BaseModel):
    name: str
    status: str
    evidence: str
    last_checked_at: datetime | None = None


class PricingInput(BaseModel):
    asset: str
    horizon: str
    resolved_count_by_asset: int = 0
    accuracy_by_asset: float | None = None
    resolved_count_by_horizon: int = 0
    accuracy_by_horizon: float | None = None
    freshness: Freshness = Freshness.FRESH
    demand: int = 0


class PriceRecord(BaseModel):
    base_price: float
    multipliers: dict[str, float]
    formula_version: str
    final_price: float
    timestamp: datetime
    min_price: float
    max_price: float
    classification: str


class TreasuryEntry(BaseModel):
    entry_id: str
    kind: str
    reference_id: str
    amount: float
    currency: str
    status: str
    created_at: datetime
    metadata: dict[str, Any] = {}


class JournalEntry(BaseModel):
    entry_id: int
    event_type: str
    entity_id: str
    payload: dict[str, Any]
    created_at: datetime