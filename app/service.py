from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .canonical import sha256_json
from .config import Settings
from .db import Database
from .engine import SignalEngine
from .market import BinanceSpotMarket, ProviderError
from .models import SignalState
from .payments import X402PaymentService


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MarketplaceService:
    def __init__(self, db: Database, engine: SignalEngine, payments: X402PaymentService, settings: Settings):
        self.db = db
        self.engine = engine
        self.payments = payments
        self.settings = settings

    def purchase(self, signal_id: str, idempotency_key: str, payment_header: str | None, resource: str) -> tuple[int, dict[str, Any], dict[str, str]]:
        signal = self.db.fetchone("SELECT * FROM signals WHERE signal_id=?", (signal_id,))
        if not signal:
            return 404, {"error": "signal not found"}, {}
        existing = self.db.fetchone("SELECT * FROM purchases WHERE idempotency_key=?", (idempotency_key,))
        if existing:
            return self._purchase_response(existing["purchase_id"], resource, signal)
        purchase_id = str(uuid.uuid4())
        created = now_iso()
        self.db.execute(
            "INSERT INTO purchases(purchase_id, signal_id, state, idempotency_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (purchase_id, signal_id, "PAYMENT_REQUIRED", idempotency_key, created, created),
        )
        self.db.execute(
            "INSERT INTO payments(purchase_id, status, verification, amount, currency, network, provider, payment_reference, transaction_hash, evidence_json, created_at, verified_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (purchase_id, "PAYMENT_REQUIRED", "UNVERIFIED", str(signal["listed_price"]), signal["currency"], None, None, None, None, "{}", created, None),
        )
        requirements = self.payments.requirements(resource, float(signal["listed_price"]))
        self.db.event("PAYMENT_REQUIRED", purchase_id, requirements, created)
        self.db.journal("PURCHASE_INITIATED", purchase_id, {"signal_id": signal_id, "amount": signal["listed_price"]}, created)
        if not payment_header:
            return 402, {"error": "payment required", "purchase_id": purchase_id, "payment_requirements": requirements}, {"PAYMENT-REQUIRED": json.dumps(requirements)}
        self.db.execute("UPDATE payments SET status=? WHERE purchase_id=?", ("VERIFYING", purchase_id))
        result = self.payments.verify_and_settle(payment_header, requirements)
        self.db.execute(
            "UPDATE payments SET status=?, verification=?, network=?, provider=?, payment_reference=?, transaction_hash=?, evidence_json=?, verified_at=? WHERE purchase_id=?",
            (result.get("status", "UNKNOWN"), result.get("verification", "UNVERIFIED"), result.get("network"), result.get("provider"),
             result.get("payment_reference"), result.get("transaction_hash"), json.dumps(result.get("evidence", {}), sort_keys=True), result.get("verified_at"), purchase_id),
        )
        self.db.execute("UPDATE purchases SET state=?, updated_at=? WHERE purchase_id=?", (result.get("status", "UNKNOWN"), now_iso(), purchase_id))
        self.db.journal("PAYMENT_VERIFIED", purchase_id, {"status": result.get("status"), "verification": result.get("verification")}, now_iso())
        if result.get("status") != "PAID" or result.get("verification") != "VERIFIED":
            return 402, {"error": "payment not verified", "purchase_id": purchase_id, "payment_status": result}, {"PAYMENT-REQUIRED": json.dumps(requirements)}
        return self._deliver(purchase_id, signal)

    def _purchase_response(self, purchase_id: str, resource: str, signal: Any) -> tuple[int, dict[str, Any], dict[str, str]]:
        payment = self.db.fetchone("SELECT * FROM payments WHERE purchase_id=?", (purchase_id,))
        if payment and payment["status"] == "PAID" and payment["verification"] == "VERIFIED":
            delivery = self.db.fetchone("SELECT * FROM deliveries WHERE purchase_id=?", (purchase_id,))
            if delivery:
                return 200, json.loads(delivery["artifact_json"]), {}
        requirements = self.payments.requirements(resource, float(signal["listed_price"]))
        return 402, {"error": "payment required", "purchase_id": purchase_id, "payment_requirements": requirements}, {"PAYMENT-REQUIRED": json.dumps(requirements)}

    def _deliver(self, purchase_id: str, signal: Any) -> tuple[int, dict[str, Any], dict[str, str]]:
        existing = self.db.fetchone("SELECT * FROM deliveries WHERE purchase_id=?", (purchase_id,))
        if existing:
            return 200, json.loads(existing["artifact_json"]), {}
        passport = json.loads(signal["passport_json"])
        artifact = {"purchase_id": purchase_id, "signal_id": signal["signal_id"], "passport": passport, "delivery": {"delivered_at": now_iso(), "payment_verified": True}}
        artifact_hash = sha256_json(artifact)
        self.db.execute(
            "INSERT INTO deliveries(purchase_id, signal_id, artifact_json, delivered_at, artifact_hash) VALUES (?, ?, ?, ?, ?)",
            (purchase_id, signal["signal_id"], json.dumps(artifact, sort_keys=True), now_iso(), artifact_hash),
        )
        self.db.execute("UPDATE purchases SET state=?, updated_at=? WHERE purchase_id=?", ("PAID", now_iso(), purchase_id))
        if signal["state"] == SignalState.LISTED.value:
            self.db.execute("UPDATE signals SET state=? WHERE signal_id=?", (SignalState.DELIVERED.value, signal["signal_id"]))
        self.db.event("SIGNAL_DELIVERED", purchase_id, {"artifact_hash": artifact_hash, "signal_hash": signal["signal_hash"]}, now_iso())
        self.db.journal("SIGNAL_DELIVERED", purchase_id, {"artifact_hash": artifact_hash}, now_iso())
        return 200, artifact, {}

    def reputation(self) -> dict[str, Any]:
        rows = self.db.fetchall("SELECT outcome_json FROM outcomes")
        outcomes = [json.loads(row["outcome_json"]) for row in rows]
        resolved = [row for row in outcomes if row.get("directional_result") in {"CORRECT", "INCORRECT", "NEUTRAL"}]
        correct = sum(1 for row in resolved if row["directional_result"] == "CORRECT")
        result: dict[str, Any] = {
            "published_signals": len(self.db.fetchall("SELECT signal_id FROM signals")),
            "resolved_signals": len(resolved),
            "correct_signals": correct,
            "incorrect_signals": sum(1 for row in resolved if row["directional_result"] == "INCORRECT"),
            "unresolved_signals": len(outcomes) - len(resolved),
            "n": len(resolved),
        }
        result["status"] = "INSUFFICIENT_SAMPLE" if len(resolved) < self.settings.min_reputation_sample else "SUFFICIENT_SAMPLE"
        result["accuracy"] = None if result["status"] == "INSUFFICIENT_SAMPLE" else correct / len(resolved) if resolved else None
        return result