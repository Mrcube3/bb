from __future__ import annotations

import json
import threading
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import Database
from .engine import SignalEngine
from .market import BinanceSpotMarket, ProviderError
from .payments import X402PaymentService
from .pricing import PricingEngine
from .resolver import OutcomeResolver
from .service import MarketplaceService


db = Database(settings.db_file)
market = BinanceSpotMarket(settings)
pricing_engine = PricingEngine(settings)
engine = SignalEngine(db, market, settings, pricing=pricing_engine)
payments = X402PaymentService(settings)
marketplace = MarketplaceService(db, engine, payments, settings)
resolver = OutcomeResolver(db, market, settings)
app = FastAPI(title="PROMETHEUS", version="0.1.0", description="Auditable machine-to-machine market intelligence")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    with open("static/index.html", encoding="utf-8") as handle:
        return handle.read()


@app.get("/health")
def health() -> dict[str, Any]:
    return {"service": "PROMETHEUS", "status": "ok", "environment": settings.environment, "database": "VERIFIED_LOCAL"}


@app.get("/provider-status")
def provider_status() -> dict[str, Any]:
    providers = [
        {"name": "sqlite", "status": "VERIFIED_LOCAL", "evidence": "database initialized"},
        {"name": "x402", "status": "VERIFIED_LOCAL" if settings.payments_configured else "UNAVAILABLE", "evidence": "configured facilitator and settlement requirements" if settings.payments_configured else "no facilitator/network/asset/payTo configured"},
        {"name": "binance_public_market", "status": "ADAPTER_ONLY", "evidence": "official REST paths implemented; live connectivity must be verified in deployment"},
    ]
    try:
        market.ping()
        providers[2]["status"] = "VERIFIED_LIVE"
        providers[2]["evidence"] = "GET /api/v3/ping succeeded"
    except ProviderError as exc:
        providers[2]["evidence"] = str(exc)
    return {"providers": providers}


@app.get("/api/marketplace/signals")
def signals() -> list[dict[str, Any]]:
    return engine.list_previews()


@app.post("/api/signals/generate")
def generate(asset: str = "BTCUSDT", horizon: str | None = None) -> dict[str, Any]:
    try:
        signal = engine.create(asset, horizon)
        return {"signal_id": signal.signal_id, "state": "LISTED", "preview": next(item for item in engine.list_previews() if item["signal_id"] == signal.signal_id)}
    except (ValueError, ProviderError) as exc:
        raise HTTPException(status_code=503 if isinstance(exc, ProviderError) else 400, detail=str(exc))


@app.get("/api/marketplace/signals/{signal_id}/preview")
def preview(signal_id: str) -> dict[str, Any]:
    row = engine.get(signal_id)
    if not row:
        raise HTTPException(404, "signal not found")
    return json.loads(row["preview_json"])


@app.post("/api/marketplace/signals/{signal_id}/purchase")
def purchase(signal_id: str, request: Request, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), payment_signature: str | None = Header(default=None, alias="PAYMENT-SIGNATURE")) -> JSONResponse:
    key = idempotency_key or f"request:{request.headers.get('x-request-id', '')}:{signal_id}"
    status, body, headers = marketplace.purchase(signal_id, key, payment_signature, str(request.url))
    return JSONResponse(status_code=status, content=body, headers=headers)


@app.get("/api/purchases/{purchase_id}")
def purchase_status(purchase_id: str) -> dict[str, Any]:
    row = db.fetchone(
        "SELECT p.*, pay.status AS payment_status, pay.verification FROM purchases p LEFT JOIN payments pay ON p.purchase_id=pay.purchase_id WHERE p.purchase_id=?",
        (purchase_id,),
    )
    if not row:
        raise HTTPException(404, "purchase not found")
    return dict(row)


@app.get("/api/purchases/{purchase_id}/delivery")
def delivery(purchase_id: str) -> dict[str, Any]:
    row = db.fetchone("SELECT * FROM deliveries WHERE purchase_id=?", (purchase_id,))
    if not row:
        raise HTTPException(404, "delivery not available")
    return json.loads(row["artifact_json"])


@app.get("/api/reputation")
def reputation() -> dict[str, Any]:
    return marketplace.reputation()


@app.post("/api/admin/resolve-due")
def resolve_due() -> dict[str, Any]:
    return {"resolved": resolver.resolve_due()}


@app.get("/api/journal")
def journal(signal_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    entries = db.get_journals(signal_id, limit)
    return {"entries": entries, "count": len(entries)}


@app.get("/api/treasury")
def treasury() -> dict[str, Any]:
    from .treasury import Treasury
    t = Treasury(db, settings)
    return t.outstanding()


@app.get("/api/events")
def events(entity_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    if entity_id:
        rows = db.fetchall("SELECT * FROM events WHERE entity_id=? ORDER BY event_id DESC LIMIT ?", (entity_id, limit))
    else:
        rows = db.fetchall("SELECT * FROM events ORDER BY event_id DESC LIMIT ?", (limit,))
    return {"events": [dict(r) for r in rows], "count": len(rows)}


def _scheduler() -> None:
    while True:
        try:
            resolver.resolve_due()
        finally:
            time.sleep(settings.list_interval_seconds)


@app.on_event("startup")
def start_scheduler() -> None:
    if settings.enable_scheduler:
        threading.Thread(target=_scheduler, daemon=True, name="prometheus-resolver").start()