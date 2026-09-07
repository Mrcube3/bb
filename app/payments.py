from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .config import Settings


class X402PaymentService:
    """x402 v2 payment adapter with official SDK integration where possible."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._sdk_available = False
        try:
            import x402  # noqa: F401
            self._sdk_available = True
        except ImportError:
            pass

    def requirements(self, resource: str, amount: float) -> dict[str, Any]:
        if not self.settings.payments_configured:
            return {"x402Version": 2, "accepts": [], "error": "PAYMENT_PROVIDER_UNAVAILABLE", "classification": "UNAVAILABLE"}
        amount_minor = str(int(round(amount * 1_000_000)))
        return {
            "x402Version": 2,
            "accepts": [{
                "scheme": self.settings.x402_scheme,
                "network": self.settings.x402_network,
                "asset": self.settings.x402_asset,
                "amount": amount_minor,
                "payTo": self.settings.x402_pay_to,
                "resource": resource,
                "description": "PROMETHEUS protected market intelligence",
                "mimeType": "application/json",
                "maxTimeoutSeconds": 120,
            }],
        }

    def verify_and_settle(self, payment_header: str, requirements: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.payments_configured:
            return {"status": "UNKNOWN", "verification": "UNAVAILABLE", "provider": "BINANCE_X402", "evidence": {"reason": "provider not configured"}}
        if self._sdk_available:
            return self._verify_sdk(payment_header, requirements)
        return self._verify_raw(payment_header, requirements)

    def _verify_sdk(self, payment_header: str, requirements: dict[str, Any]) -> dict[str, Any]:
        try:
            from x402.http import FacilitatorConfig, HTTPFacilitatorClient
            facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=self.settings.facilitator_url))
            accept = requirements["accepts"][0] if requirements.get("accepts") else {}
            payload = self._decode_header(payment_header)
            verify_result = self._facilitator_verify(facilitator, payload, accept)
            if not verify_result.get("isValid"):
                return {"status": "FAILED", "verification": "REJECTED", "provider": "X402_SDK", "evidence": verify_result}
            settle_result = self._facilitator_settle(facilitator, payload, accept)
            success = bool(settle_result.get("success") or settle_result.get("settled"))
            return {
                "status": "PAID" if success else "UNKNOWN",
                "verification": "VERIFIED" if success else "UNVERIFIED",
                "provider": "X402_SDK",
                "payment_reference": settle_result.get("paymentId"),
                "transaction_hash": settle_result.get("transactionHash"),
                "network": accept.get("network"),
                "evidence": {"verify": verify_result, "settle": settle_result},
                "verified_at": datetime.now(timezone.utc).isoformat() if success else None,
            }
        except Exception as exc:
            return {"status": "UNKNOWN", "verification": "UNVERIFIED", "provider": "X402_SDK", "evidence": {"error": str(exc)}}

    def _facilitator_verify(self, facilitator: Any, payload: dict[str, Any], accept: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"paymentPayload": payload, "paymentRequirements": accept}, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.settings.x402_pay_to:
            headers["X-Api-Key"] = self.settings.x402_pay_to
        return self._post(self.settings.facilitator_url + "/verify", body, headers)

    def _facilitator_settle(self, facilitator: Any, payload: dict[str, Any], accept: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"paymentPayload": payload, "paymentRequirements": accept}, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.settings.x402_pay_to:
            headers["X-Api-Key"] = self.settings.x402_pay_to
        return self._post(self.settings.facilitator_url + "/settle", body, headers)

    def _verify_raw(self, payment_header: str, requirements: dict[str, Any]) -> dict[str, Any]:
        payload = self._decode_header(payment_header)
        body = json.dumps({"paymentPayload": payload, "paymentRequirements": requirements["accepts"][0]}, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        verify = self._post(self.settings.facilitator_url + "/verify", body, headers)
        if not verify.get("isValid", verify.get("valid", False)):
            return {"status": "FAILED", "verification": "REJECTED", "provider": "BINANCE_X402", "evidence": verify}
        settle = self._post(self.settings.facilitator_url + "/settle", body, headers)
        success = bool(settle.get("success", settle.get("settled", False)))
        return {
            "status": "PAID" if success else "UNKNOWN", "verification": "VERIFIED" if success else "UNVERIFIED",
            "provider": "BINANCE_X402", "payment_reference": settle.get("paymentId"),
            "transaction_hash": settle.get("transactionHash"), "network": requirements["accepts"][0]["network"],
            "evidence": {"verify": verify, "settle": settle},
            "verified_at": datetime.now(timezone.utc).isoformat() if success else None,
        }

    @staticmethod
    def _decode_header(value: str) -> dict[str, Any]:
        import base64
        try:
            return json.loads(base64.b64decode(value).decode())
        except Exception as exc:
            raise ValueError(f"invalid x402 base64 JSON: {exc}") from exc

    @staticmethod
    def _post(url: str, body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode())
        except Exception as exc:
            return {"error": f"payment provider request failed: {type(exc).__name__}: {exc}"}