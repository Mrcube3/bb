# Binance Capability Matrix

## Public Market Data (Used by PROMETHEUS)

| Endpoint | Status | Auth Required | Rate Limit |
|----------|--------|---------------|------------|
| GET /api/v3/ping | VERIFIED_LIVE | None | 1200/min |
| GET /api/v3/ticker/bookTicker | VERIFIED_LIVE | None | 1200/min |
| GET /api/v3/klines | VERIFIED_LIVE | None | 1200/min |
| GET /api/v3/ticker/price | VERIFIED_LIVE | None | 1200/min |
| GET /api/v3/depth | VERIFIED_LIVE | None | 1200/min |
| GET /api/v3/trades | VERIFIED_LIVE | None | 1200/min |

## MCP Server (Not Used)

| Capability | Status | Notes |
|------------|--------|-------|
| OAuth Authentication | ADAPTER_ONLY | Requires browser flow |
| Account Access | NOT_USED | Not needed for PROMETHEUS |
| Trading | NOT_USED | Not needed for PROMETHEUS |
| Wallet | NOT_USED | Not needed for PROMETHEUS |

## x402 Payments (Being Integrated)

| Component | Status | Notes |
|-----------|--------|-------|
| Testnet Facilitator | SIMULATION | `https://x402.org/facilitator` |
| Mainnet Facilitator | ADAPTER_ONLY | Coinbase/PayAI |
| Python SDK | ADAPTER_ONLY | `pip install "x402[fastapi]"` |
| Exact Scheme | ADAPTER_ONLY | Fixed-price payments |
| Upto Scheme | NOT_IMPLEMENTED | Usage-based (future) |

## Agentic Wallet (Not Used)

| Capability | Status | Notes |
|------------|--------|-------|
| Wallet Creation | NOT_USED | Not needed |
| Fund Management | NOT_USED | Not needed |
| Transaction Signing | NOT_USED | Not needed |

## Skills Hub (Not Used)

| Skill | Status | Notes |
|-------|--------|-------|
| Trading Skills | NOT_USED | Not needed |
| Analysis Skills | NOT_USED | Not needed |
| Custom Skills | NOT_USED | Not needed |

## Integration Decision Summary

| Component | Decision | Reason |
|-----------|----------|--------|
| Public Market Data | INTEGRATE | Core requirement for signal generation |
| MCP Server | SKIP | Requires OAuth, not needed |
| x402 Payments | INTEGRATE | Core requirement for marketplace |
| Agentic Wallet | SKIP | Not needed for signal economy |
| Skills Hub | SKIP | Not needed for signal economy |
| Trading API | SKIP | No account access needed |
