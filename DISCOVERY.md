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
| Seller (PROMETHEUS) | ADAPTER_ONLY | Custom implementation exists; needs SDK integration |
| Buyer Agent | ADAPTER_ONLY | Custom implementation exists; needs SDK integration |
| Facilitator | SIMULATION | Using `https://x402.org/facilitator` for testnet |

## Repository Audit

### Existing Implementation

| Module | Status | Notes |
|--------|--------|-------|
| FastAPI App | VERIFIED_LOCAL | Basic structure works |
| SQLite Database | VERIFIED_LOCAL | Schema initialized correctly |
| Binance Market Data | VERIFIED_LIVE | Public REST API working |
| Quant Engine | VERIFIED_LOCAL | Deterministic calculations correct |
| Signal Engine | VERIFIED_LOCAL | State machine implemented |
| Canonical Hashing | VERIFIED_LOCAL | SHA256 canonical JSON working |
| Payments (Custom) | ADAPTER_ONLY | Needs x402 SDK integration |
| Outcome Resolver | VERIFIED_LOCAL | Basic resolution working |
| Marketplace Service | VERIFIED_LOCAL | Basic purchase flow working |
| Buyer Agent | ADAPTER_ONLY | Needs proper x402 flow |
| Dashboard | VERIFIED_LOCAL | Basic UI functional |

### Missing Components

1. Official x402 Python SDK integration
2. Enhanced evidence validator (claim validation)
3. Reputation-based pricing engine
4. Complete signal passport
5. Proper idempotency across all endpoints
6. Real-time dashboard updates
7. Comprehensive error handling

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
| Market Data | VERIFIED_LIVE | Use Binance public REST API |
| Quant Engine | VERIFIED_LOCAL | Deterministic Python calculations |
| Signal Engine | VERIFIED_LOCAL | Pydantic validation + state machine |
| Evidence Validator | VERIFIED_LOCAL | Claim-to-evidence key validation |
| Passport Engine | VERIFIED_LOCAL | SHA256 canonical hashing |
| Pricing Engine | VERIFIED_LOCAL | Bounded deterministic pricing |
| x402 Payments | ADAPTER_ONLY | Integrate official Python SDK |
| Delivery Engine | VERIFIED_LOCAL | Artifact delivery after payment |
| Outcome Engine | VERIFIED_LOCAL | Binance price resolution |
| Reputation Engine | VERIFIED_LOCAL | Outcome-based scoring |
| Dashboard | VERIFIED_LOCAL | Real-time API polling |
| Buyer Agent | ADAPTER_ONLY | Independent process |

## Next Steps

1. Integrate official x402 Python SDK
2. Enhance evidence validator
3. Improve pricing engine
4. Complete signal passport
5. End-to-end testing
