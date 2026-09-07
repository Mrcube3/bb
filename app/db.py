from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS signals (
  signal_id TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  created_at TEXT NOT NULL,
  published_at TEXT,
  asset TEXT NOT NULL,
  horizon TEXT NOT NULL,
  horizon_seconds INTEGER NOT NULL,
  listed_price REAL NOT NULL,
  currency TEXT NOT NULL,
  preview_json TEXT NOT NULL,
  passport_json TEXT NOT NULL,
  signal_json TEXT NOT NULL,
  snapshot_hash TEXT NOT NULL,
  quant_hash TEXT NOT NULL,
  signal_hash TEXT NOT NULL,
  outcome_due_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_state_due ON signals(state, outcome_due_at);
CREATE TABLE IF NOT EXISTS purchases (
  purchase_id TEXT PRIMARY KEY,
  signal_id TEXT NOT NULL,
  state TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(signal_id) REFERENCES signals(signal_id)
);
CREATE TABLE IF NOT EXISTS payments (
  purchase_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  verification TEXT NOT NULL,
  amount TEXT NOT NULL,
  currency TEXT NOT NULL,
  network TEXT,
  provider TEXT,
  payment_reference TEXT,
  transaction_hash TEXT,
  evidence_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  verified_at TEXT,
  FOREIGN KEY(purchase_id) REFERENCES purchases(purchase_id)
);
CREATE TABLE IF NOT EXISTS deliveries (
  purchase_id TEXT PRIMARY KEY,
  signal_id TEXT NOT NULL,
  artifact_json TEXT NOT NULL,
  delivered_at TEXT NOT NULL,
  artifact_hash TEXT NOT NULL,
  FOREIGN KEY(purchase_id) REFERENCES purchases(purchase_id)
);
CREATE TABLE IF NOT EXISTS outcomes (
  outcome_id TEXT PRIMARY KEY,
  signal_id TEXT NOT NULL UNIQUE,
  outcome_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(signal_id) REFERENCES signals(signal_id)
);
CREATE TABLE IF NOT EXISTS events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS treasury (
  entry_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  reference_id TEXT NOT NULL,
  amount REAL NOT NULL,
  currency TEXT NOT NULL,
  status TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journals (
  entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  sequence INTEGER NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._in_memory = str(path) in (":memory:", "")
        if self._in_memory:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(SCHEMA)
        else:
            Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
            with self._open() as conn:
                conn.executescript(SCHEMA)
            self._migrate()

    @contextmanager
    def _open(self) -> Iterator[sqlite3.Connection]:
        if self._in_memory:
            yield self._conn
            self._conn.commit()
        else:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _migrate(self) -> None:
        with self._open() as conn:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(signals)")}
            extra = {"listed_price", "currency", "outcome_due_at"}
            for col in extra - cols:
                if col == "outcome_due_at":
                    conn.execute("ALTER TABLE signals ADD COLUMN outcome_due_at TEXT")
                elif col in ("listed_price", "currency"):
                    conn.execute(f"ALTER TABLE signals ADD COLUMN {col} TEXT")
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(purchases)")}
            if "updated_at" not in cols:
                conn.execute("ALTER TABLE purchases ADD COLUMN updated_at TEXT DEFAULT ''")

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self._open() as conn:
            conn.execute(sql, params)

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._open() as conn:
            return conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._open() as conn:
            return conn.execute(sql, params).fetchall()

    def event(self, event_type: str, entity_id: str, payload: dict[str, Any], created_at: str) -> None:
        self.execute(
            "INSERT INTO events(event_type, entity_id, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (event_type, entity_id, json.dumps(payload, sort_keys=True, default=str), created_at),
        )

    def journal(self, event_type: str, entity_id: str, payload: dict[str, Any], created_at: str) -> None:
        self.execute(
            """INSERT INTO journals(event_type, entity_id, payload_json, created_at, sequence)
               VALUES (?, ?, ?, ?, (SELECT COALESCE(MAX(sequence), 0) + 1 FROM journals))""",
            (event_type, entity_id, json.dumps(payload, sort_keys=True, default=str), created_at),
        )

    def treasury_entry(self, entry_id: str, kind: str, reference_id: str, amount: float, currency: str, status: str, metadata: dict[str, Any], created_at: str) -> None:
        self.execute(
            "INSERT INTO treasury(entry_id, kind, reference_id, amount, currency, status, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (entry_id, kind, reference_id, amount, currency, status, json.dumps(metadata, sort_keys=True, default=str), created_at),
        )

    def get_journals(self, entity_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if entity_id:
            rows = self.fetchall(
                "SELECT entry_id, event_type, entity_id, payload_json, created_at FROM journals WHERE entity_id=? ORDER BY sequence DESC LIMIT ?",
                (entity_id, limit),
            )
        else:
            rows = self.fetchall(
                "SELECT entry_id, event_type, entity_id, payload_json, created_at FROM journals ORDER BY sequence DESC LIMIT ?",
                (limit,),
            )
        return [{"entry_id": r["entry_id"], "event_type": r["event_type"], "entity_id": r["entity_id"],
                 "payload": json.loads(r["payload_json"]), "created_at": r["created_at"]} for r in rows]

    def get_treasury(self) -> list[dict[str, Any]]:
        rows = self.fetchall("SELECT * FROM treasury ORDER BY created_at DESC")
        return [{k: (json.loads(r["metadata_json"]) if k == "metadata_json" else r[k]) for k in r.keys()}
                for r in rows]