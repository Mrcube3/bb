# PROMETHEUS — An Autonomous Signal Economy

**Tagline: Predict. Sell. Prove. Repeat.**

PROMETHEUS is a deterministic, auditable marketplace where prediction signals are
generated, cryptographically frozen, priced, sold (via x402 payments), delivered,
and resolved against real market outcomes — with every agent's reputation and the
treasury tracked immutably in an append-only journal.

Built for the **Binance Agent OS Mini Hackathon** (Track A).

- **Deadline:** September 8, 2026 — 23:59 UTC
- **Stack:** Python 3.12 / FastAPI / Pydantic / SQLite (WAL) / vanilla HTML dashboard / Docker
- **Market data:** Binance public REST API (`https://data-api.binance.vision`) — verified live
- **Payments:** x402 v2 (HTTP 402) wire protocol

## How it works

1. **Observe** — the market adapter snapshots live Binance ticker/order-book data.
2. **Quantify** — a deterministic quant engine computes features (RSI, EMA cross,
   ATR, realized volatility, order-book imbalance, volume change, ...).
3. **Predict** — a deterministic signal generator emits a LONG / SHORT / NEUTRAL
   signal with an explicit thesis and evidence key list.
4. **Freeze** — the signal and its evidence are hashed (SHA-256 over canonical JSON)
   into an immutable passport before it is ever listed.
5. **List** — the signal is priced deterministically (bounded, reputation-aware) and
   published to the marketplace.
6. **Sell** — an independent buyer agent requests the signal, the server responds
   `402 Payment Required` with a `PAYMENT-REQUIRED` header; after verification the
   evidence is delivered.
7. **Prove** — when the horizon elapses, the raw outcome is resolved from real
   Binance candles and the prediction is scored CORRECT / INCORRECT / NEUTRAL.
8. **Repeat** — reputation is recomputed from verified outcomes; pricing adjusts;
   the company ledger (treasury) and journal are updated.

## Quickstart (local)

Requires Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env        # optional; all values have defaults
uvicorn app.api:app --reload
```

Open `http://127.0.0.1:8000` for the dashboard, or `http://127.0.0.1:8000/docs`
for the OpenAPI UI.

## Run an end-to-end loop

```bash
# 1. Generate and list a live signal (real Binance prices)
curl -X POST "http://127.0.0.1:8000/api/signals/generate?asset=BTCUSDT&horizon=10m"
curl http://127.0.0.1:8000/api/marketplace/signals

# 2. Buy it (the server returns 402 + PAYMENT-REQUIRED)
curl -X POST \
  -H "Idempotency-Key: demo-1" \
  http://127.0.0.1:8000/api/marketplace/signals/<SIGNAL_ID>/purchase

# 3. Resolve due outcomes (or wait for the scheduler)
curl -X POST http://127.0.0.1:8000/api/admin/resolve-due

# 4. Inspect reputation, treasury, immutable journal
curl http://127.0.0.1:8000/api/reputation
curl http://127.0.0.1:8000/api/treasury
curl http://127.0.0.1:8000/api/journal

# 5. Use the independent buyer agent
python buyer_agent.py --base-url http://127.0.0.1:8000
```

## API summary

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Service + DB status |
| GET | `/provider-status` | Status of each external dependency |
| GET | `/api/marketplace/signals` | List listed signals (previews) |
| POST | `/api/signals/generate` | Create + freeze + list a new signal |
| GET | `/api/signals/{id}/preview` | Full preview with price/reputation |
| POST | `/api/marketplace/signals/{id}/purchase` | x402 purchase flow |
| GET | `/api/purchases/{id}` | Purchase detail / payment status |
| GET | `/api/purchases/{id}/delivery` | Delivered artifact (after payment verification) |
| GET | `/api/reputation` | Reputation summary |
| POST | `/api/admin/resolve-due` | Resolve all due outcomes |
| GET | `/api/journal` | Immutable event journal |
| GET | `/api/treasury` | Economic ledger |

Signals follow a strict state machine:
`DRAFT → LISTED → PURCHASED → DELIVERED → AWAITING_OUTCOME → VERIFIED`,
with fraud/impossible transitions rejected.

## Configuration

All settings live in `app/config.py` and can be overridden via environment
variables (see `.env.example`).

Key ones:

| Variable | Default | Meaning |
|----------|---------|---------|
| `PROMETHEUS_DB_PATH` | `./prometheus.db` | SQLite file (WAL mode) |
| `PROMETHEUS_ASSETS` | `BTCUSDT,ETHUSDT,SOLUSDT` | Tradable assets |
| `PROMETHEUS_HORIZONS` | `10M,15M,1H,4H,24H` | Outcome horizons |
| `PROMETHEUS_BASE_PRICE` | `0.01` | Cold-start price (USDC) |
| `PROMETHEUS_MIN_REPUTATION_SAMPLE` | `20` | Minimum resolved outcomes before reputation-based pricing |
| `PROMETHEUS_FACILITATOR_URL` | *(empty)* | x402 facilitator (e.g. `https://x402.org/facilitator`) |
| `PROMETHEUS_X402_NETWORK` | *(empty)* | x402 network, e.g. `eip155:84532` |
| `PROMETHEUS_X402_ASSET` | `USDC` | Payment asset |
| `PROMETHEUS_X402_PAY_TO` | *(empty)* | Seller address — required to enable payments |
| `PROMETHEUS_ENABLE_SCHEDULER` | `true` | Auto-generate + auto-resolve loop |

When a facilitator + network + pay-to address are configured, `/provider-status`
reports the x402 provider as `VERIFIED_TESTNET` (or `VERIFIED_MAINNET`) and real
payment verification/settlement is attempted. Without them, purchases still run the
full 402 flow but classify as `UNAVAILABLE`.

## Docker

```bash
docker build -t prometheus .
docker run -p 8000:8000 -v prometheus-data:/data prometheus
```

## Testing

```bash
python tests/test_integration.py
```

The suite drives the real application (live Binance market data, in-memory DB):

- 5 consecutive valid signals must pass evidence validation and list
- a nonexistent evidence key must be rejected (`UNSUPPORTED_CLAIM`)
- purchase flow returns 402 with correct headers; idempotency holds
- outcome resolution, reputation, treasury, and journal all update

## Design principles

1. **Code is authoritative** — the LLM is advisory; no model output can set prices.
2. **Fail closed** — unknown states are never treated as success (no null→0, no
   mock→integration, no untested→verified).
3. **Immutable history** — signals are write-once; a journal records every event.
4. **Real integrations only** — every dependency is classified
   (`VERIFIED_LIVE` / `VERIFIED_TESTNET` / `VERIFIED_LOCAL` / `SIMULATION` /
   `MOCK` / `ADAPTER_ONLY` / `UNAVAILABLE`); no mock presented as working.
5. **Deterministic pricing** — bounded, reproducible, reputation-aware.

See `DISCOVERY.md` and `BINANCE_CAPABILITY_MATRIX.md` for the full dependency audit.