"""End-to-end integration test for the PROMETHEUS lifecycle.

Exercises the actual application modules (not mocks) to verify:
1. Market observation
2. Quant analysis
3. Signal generation + freezing
4. Purchasing (402 / payment required)
5. Idempotent purchases
6. Outcome resolution
7. Reputation updates
8. Journal / treasury recording
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.config import Settings, settings
from app.db import Database
from app.evidence import EvidenceError, EvidenceValidator
from app.market import BinanceSpotMarket
from app.models import SignalState
from app.payments import X402PaymentService
from app.pricing import PricingEngine
from app.engine import SignalEngine
from app.resolver import OutcomeResolver
from app.service import MarketplaceService
from app.treasury import Treasury
from app.quant import build_quant_packet


def test_signal_lifecycle() -> None:
    db = Database(":memory:")
    market = BinanceSpotMarket(settings)
    pricing = PricingEngine(settings)
    validator = EvidenceValidator()
    engine = SignalEngine(db, market, settings, pricing=pricing, validator=validator)
    payments = X402PaymentService(settings)
    marketplace = MarketplaceService(db, engine, payments, settings)
    resolver = OutcomeResolver(db, market, settings)
    treasury = Treasury(db, settings)

    # 1. Generate a signal
    signal = engine.create("BTCUSDT", "10m")
    assert signal.state == SignalState.DRAFT
    row = db.fetchone("SELECT * FROM signals WHERE signal_id=?", (signal.signal_id,))
    assert row["state"] == SignalState.LISTED.value, "signal should be LISTED after freeze"
    print(f"[PASS] Signal frozen and listed: {signal.signal_id[:8]}")

    # 2. Evidence validation
    snapshot = __import__("json").loads(row["signal_json"])
    assert "evidence_keys" in snapshot
    assert all(k in json.loads(row["passport_json"])["quant_packet"]["evidence"] for k in snapshot["evidence_keys"])
    print("[PASS] Evidence keys validated against quant packet")

    # 3. Verify hashes in passport
    passport = json.loads(row["passport_json"])
    assert passport["signal_hash"]
    assert passport["snapshot_hash"]
    assert passport["quant_hash"]
    assert passport["listed_price"] >= settings.min_price
    assert passport["listed_price"] <= settings.max_price
    print(f"[PASS] Passport frozen with hashes. Price: {passport['listed_price']} {passport['currency']}")

    # 4. Purchase flow (should return 402 since no payment provider configured)
    status, body, headers = marketplace.purchase(signal.signal_id, "idem-1", None, "http://example.test/purchase")
    assert status == 402, "purchase without payment should return 402"
    assert body["error"] == "payment required"
    assert "PAYMENT-REQUIRED" in headers
    print("[PASS] Purchase correctly returns 402 Payment Required")

    # 5. Idempotency - same key, same response
    status2, body2, headers2 = marketplace.purchase(signal.signal_id, "idem-1", None, "http://example.test/purchase")
    assert status2 == 402
    assert body2.get("purchase_id") == body.get("purchase_id"), "idempotent request should return same purchase id"
    print("[PASS] Idempotent purchase returns same purchase_id")

    # 6. Purchase with signature (should fail since no provider configured)
    status3, body3, _ = marketplace.purchase(signal.signal_id, "idem-2", "invalid-signature", "http://example.test/purchase")
    assert status3 == 402, "invalid signature should still be payment-required"
    print(f"[PASS] Payment verification skipped (provider: {settings.payments_configured})")

    # 7. Treasury recording
    entry_id = treasury.record_sale(signal.signal_id, passport["listed_price"], {"status": "test"})
    outstanding = treasury.outstanding()
    assert outstanding["total"] == passport["listed_price"]
    print(f"[PASS] Treasury recorded sale: {outstanding['total']} {settings.currency}")

    # 8. Outcome resolution (force by manipulating due time - tests real resolver path)
    from datetime import timedelta
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    db.execute("UPDATE signals SET outcome_due_at=? WHERE signal_id=?", (past, signal.signal_id))
    resolved = resolver.resolve_due()
    assert len(resolved) == 1, "one outcome should be resolved"
    outcome = resolved[0]
    assert outcome["directional_result"] in {"CORRECT", "INCORRECT", "NEUTRAL"}
    print(f"[PASS] Outcome resolved: {outcome['directional_result']} (return: {outcome['raw_return']:.6f})")

    # 9. Reputation
    rep = marketplace.reputation()
    assert rep["resolved_signals"] == 1
    assert rep["n"] == 1
    assert rep["status"] == "INSUFFICIENT_SAMPLE"
    print(f"[PASS] Reputation: {rep}")

    # 10. Journal immutable history
    journals = db.get_journals(signal.signal_id)
    assert len(journals) >= 3, f"journal should have multiple entries, got {len(journals)}"
    print(f"[PASS] Journal has {len(journals)} entries for signal")

    print("\n=== ALL TESTS PASSED ===")


def test_evidence_validator_rejects_invalid() -> None:
    """Acceptance test: inject a nonexistent evidence key - it MUST be rejected."""
    db = Database(":memory:")
    market = BinanceSpotMarket(settings)
    pricing = PricingEngine(settings)
    validator = EvidenceValidator()
    engine = SignalEngine(db, market, settings, pricing=pricing, validator=validator)

    # Generate 5 valid signals
    for i in range(5):
        signal = engine.create("BTCUSDT", "10m")
        row = db.fetchone("SELECT state FROM signals WHERE signal_id=?", (signal.signal_id,))
        assert row["state"] == SignalState.LISTED.value
    print("[PASS] 5 valid signals generated")

    # Simulate invalid evidence key
    from app.quant import build_quant_packet
    snapshot = market.snapshot("BTCUSDT")
    quant = build_quant_packet(snapshot, market, settings)
    assert "fake_key_200" not in quant.evidence

    # Create a signal with invalid evidence key and confirm validation rejects it
    from app.models import Direction, Signal
    bad = Signal(
        signal_id="bad-1", created_at=datetime.now(timezone.utc), asset="BTCUSDT", venue="BINANCE_SPOT",
        direction=Direction.LONG, horizon="10m", horizon_seconds=600, confidence=0.5,
        model_provider="test", model_version="v1", prompt_schema_version="v1",
        entry_reference=quant.features["current_price"], invalidation=100,
        evidence_keys=["ema_200"], thesis="fake", risk_factors=["fake"], snapshot_reference=quant.packet_id,
        state=SignalState.DRAFT,
    )
    try:
        validator.validate(bad, quant)
        raise AssertionError("should have rejected invalid evidence key")
    except EvidenceError:
        print("[PASS] Nonexistent evidence key correctly rejected")

    print("\n=== EVIDENCE VALIDATOR TESTS PASSED ===")


if __name__ == "__main__":
    test_signal_lifecycle()
    test_evidence_validator_rejects_invalid()