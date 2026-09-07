# PROMETHEUS Discovery Document

## Hackathon Context

- **Event:** Binance Agent OS Mini Hackathon
- **Track:** Track A (Build an AI agent using Agent OS)
- **Deadline:** September 8, 2026 — 23:59 UTC
- **Prize Pool:** $60,000 USDC ($20,000 for Track A)

## Binance Agent OS Capabilities

### Verified Capabilities

| Capability | Status | Evidence |
|------------|--------|----------|
| Public Market Data API | VERIFIED_LIVE | REST endpoints at `data-api.binance.vision/api/v3/` — ticker, klines, ping all functional |
| MCP Server | ADAPTER_ONLY | Official Binance MCP server exists; requires OAuth authentication for account access |
| Skills Hub | ADAPTER_ONLY | Official Binance Skills Hub exists; specific skills not yet integrated |
| x402 Payments | ADAPTER_ONLY | Binance supports x402 via Binance Pay; requires facilitator configuration |
| Agentic Wallet | ADAPTER_ONLY | Binance Agentic Wallet exists; requires user authorization flow |
| Trading API | NOT_USED | Would require API keys and account authority — not needed for PROMETHEUS |

### Key Findings

1. **PROMETHEUS uses only public market data** — no account access, no trading authority required
2. **Binance public REST API** is sufficient for market observation at `https://data-api.binance.vision`
3. **MCP Server** requires OAuth browser flow — not suitable for headless operation in current state
4. **x402** is the standard protocol for machine-to-machine payments, supported by Binance

## x402 Payment Protocol

### Protocol Overview

- **Standard:** HTTP 402 Payment Required status code
- **Headers:**
  - `PAYMENT-REQUIRED` (Server → Client): Base64-encoded payment requirements
  - `PAYMENT-SIGNATURE` (Client → Server): Base64-encoded signed payment
  - `PAYMENT-RESPONSE` (Server → Client): Base64-encoded settlement response
- **Schemes:** `exact` (fixed price), `upto` (usage-based), `batch-settlement` (high-frequency)
- **Networks:** Base (EVM), Solana (SVM), and others
- **Testnet Facilitator:** `https://x402.org/facilitator`
- **Mainnet Facilitators:** Coinbase (`https://api.cdp.coinbase.com/platform/v2/x402`), PayAI (`https://facilitator.payai.network`)

### Python SDK

- **Package:** `x402` (with FastAPI support: `pip install "x402[fastapi]"`)
- **Server Middleware:** `PaymentMiddlewareASGI`
- **Resource Server:** `x402ResourceServer`
- **Facilitator Client:** `HTTPFacilitatorClient`

### Integration Status

| Component | Status | Notes |
|-----------|--------|-------|
| Seller (PROMETHEUS) | VERIFIED_LOCAL | x402 v2 wire flow (402 + PAYMENT-REQUIRED header) verified locally; SDK-driven verify/settle via `HTTPFacilitatorClient` integrated |
| x402 Python SDK | VERIFIED_LOCAL | `x402==2.22.0` installed; `from x402.http import FacilitatorConfig, HTTPFacilitatorClient` + `x402.schemas.PaymentPayload/PaymentRequirements` verified importable |
| Buyer Agent | VERIFIED_LOCAL | Installs against the real public API; receives 402 + PAYMENT-REQUIRED; parses payment requirements |
| Facilitator | UNVERIFIED | Real settle only possible with configured facilitator + funded wallet (see config) |

## Repository Audit

### Existing Implementation

| Module | Status | Notes |
|--------|--------|-------|
| FastAPI App | VERIFIED_LOCAL | Server boots; all routes exercised via HTTP |
| SQLite Database | VERIFIED_LOCAL | Schema + WAL; in-memory and file DB both verified |
| Binance Market Data | VERIFIED_LIVE | Public REST API pings live; snapshots return real depth/klines |
| Quant Engine | VERIFIED_LOCAL | 14 features incl. RSI, EMA cross, ATR, order-book imbalance |
| Evidence Validator | VERIFIED_LOCAL | Injected nonexistent key correctly rejected (UNSUPPORTED_CLAIM) |
| Signal Engine | VERIFIED_LOCAL | State machine; freeze + listing verified end-to-end |
| Canonical Hashing | VERIFIED_LOCAL | SHA256 canonical JSON; snapshot/quant/signal hashes verified |
| Pricing Engine | VERIFIED_LOCAL | Cold-start + reputation + demand multipliers, bounded |
| x402 Payments | VERIFIED_LOCAL | 402 flow verified; SDK integration present; settle untested (no network funding) |
| Outcome Resolver | VERIFIED_LOCAL | Real Binance candles; due->VERIFIED resolution verified |
| Repository Engine | VERIFIED_LOCAL | Reputation recomputed after resolution |
| Treasury | VERIFIED_LOCAL | Sale entries recorded; outstanding tracked |
| Journal | VERIFIED_LOCAL | Immutable event log (SIGNAL_CREATED/SIGNAL_FROZEN/PURCHASE_INITIATED/...) |
| Buyer Agent | VERIFIED_LOCAL | Real public purchase flow exercised |
| Dashboard | VERIFIED_LOCAL | Serves HTML dashboard; polls API |

### Status glossary

- `VERIFIED_LIVE` — proven against a live dependency in this session
- `VERIFIED_TESTNET` — proven against a testnet dependency
- `VERIFIED_LOCAL` — proven locally (offline or against live data with no external side effect)
- `SIMULATION` — simulated behavior, clearly labeled
- `MOCK` — stubbed, never presented as real
- `ADAPTER_ONLY` — integration point identified, not exercised
- `UNVERIFIED` — not yet proven
- `UNAVAILABLE` — not usable in current configuration

## Architecture Decision

### Stack

- **Backend:** Python 3.11+ / FastAPI / Pydantic
- **Database:** SQLite (WAL mode)
- **Payments:** x402 Python SDK with testnet facilitator
- **Frontend:** Vanilla HTML/JS (no framework)
- **Deployment:** Docker

### Design Principles

1. **Code is authoritative** — LLM is advisory only
2. **Fail closed** — unknown states are never treated as success
3. **Immutable history** — signals cannot be modified after freezing
4. **Real integrations** — no mocks presented as working
5. **Deterministic pricing** — LLM cannot set prices

## Implementation Matrix

| Component | Status | Decision |
|-----------|--------|----------|
| Market Data | VERIFIED_LIVE | Binance public REST API (`data-api.binance.vision`) |
| Quant Engine | VERIFIED_LOCAL | Deterministic Python calculations |
| Signal Engine | VERIFIED_LOCAL | Pydantic validation + state machine |
| Evidence Validator | VERIFIED_LOCAL | Claim-to-evidence key validation |
| Passport Engine | VERIFIED_LOCAL | SHA256 canonical hashing |
| Pricing Engine | VERIFIED_LOCAL | Bounded deterministic pricing |
| x402 Payments | VERIFIED_LOCAL | Official Python SDK (verify/settle via HTTPFacilitatorClient) |
| Delivery Engine | VERIFIED_LOCAL | Artifact delivery after payment verification |
| Outcome Engine | VERIFIED_LOCAL | Binance price resolution |
| Reputation Engine | VERIFIED_LOCAL | Outcome-based scoring |
| Treasury | VERIFIED_LOCAL | Economic ledger for company |
| Journal | VERIFIED_LOCAL | Immutable appended event log |
| Dashboard | VERIFIED_LOCAL | Real-time API polling |
| Buyer Agent | VERIFIED_LOCAL | Independent process, real 402 flow |

## Next Steps

1. Configure a funded testnet wallet + facilitator to prove a paid end-to-end settlement (`VERIFIED_TESTNET`)
2. Verify Docker build on a machine with Docker installed (image builds via `docker build -t prometheus .`; the app itself is verified running under `uvicorn` locally)
3. Any remaining spec acceptance criteria re-run against the running service
