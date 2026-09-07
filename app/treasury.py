from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .db import Database


class Treasury:
    """Economic ledger for all monetary events."""

    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    def record(self, kind: str, reference_id: str, amount: float, status: str = "RECORDED", metadata: dict[str, Any] | None = None) -> str:
        entry_id = str(uuid.uuid4())
        self.db.treasury_entry(
            entry_id,
            kind,
            reference_id,
            amount,
            self.settings.currency,
            status,
            metadata or {},
            datetime.now(timezone.utc).isoformat(),
        )
        return entry_id

    def record_sale(self, reference_id: str, amount: float, metadata: dict[str, Any] | None = None) -> str:
        return self.record("SALE", reference_id, amount, metadata=metadata)

    def outstanding(self) -> dict[str, Any]:
        rows = self.db.get_treasury()
        total = sum(r["amount"] for r in rows if r["status"] != "VOID")
        by_kind: dict[str, float] = {}
        for r in rows:
            if r["status"] == "VOID":
                continue
            by_kind[r["kind"]] = by_kind.get(r["kind"], 0.0) + r["amount"]
        return {
            "total": total,
            "by_kind": by_kind,
            "entries": rows,
            "entry_count": len(rows),
        }