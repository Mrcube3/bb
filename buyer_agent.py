from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.request
from typing import Any


def request_json(url: str, method: str = "GET", headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any], dict[str, str]]:
    request = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode()), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode()), dict(exc.headers)


def main() -> int:
    parser = argparse.ArgumentParser(description="Independent PROMETHEUS buyer agent")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="PROMETHEUS base URL")
    parser.add_argument("--signal-id", help="Specific signal ID to purchase")
    parser.add_argument("--payment-signature", help="Base64 JSON x402 PAYMENT-SIGNATURE")
    parser.add_argument("--payment-file", help="Path to file containing payment signature JSON")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print(json.dumps({"agent": "PROMETHEUS_BUYER", "status": "DISCOVERING", "base_url": base}, indent=2))

    status, listings, _ = request_json(f"{base}/api/marketplace/signals")
    if status != 200:
        print(json.dumps({"status": "DISCOVERY_FAILED", "http_status": status, "response": listings}, indent=2))
        return 1

    if not listings:
        print(json.dumps({"status": "NO_SIGNALS", "message": "No listed signals available"}, indent=2))
        return 1

    selected = next((item for item in listings if item["signal_id"] == args.signal_id), listings[0]) if args.signal_id else listings[0]
    print(json.dumps({"status": "SELECTED", "signal_id": selected["signal_id"], "asset": selected["asset"], "horizon": selected["horizon"], "listed_price": selected["listed_price"], "currency": selected["currency"]}, indent=2))

    idempotency_key = f"buyer-agent-{selected['signal_id']}"
    headers = {"Idempotency-Key": idempotency_key}

    payment_sig = args.payment_signature
    if not payment_sig and args.payment_file:
        try:
            with open(args.payment_file) as f:
                payment_sig = f.read().strip()
        except Exception as exc:
            print(json.dumps({"status": "PAYMENT_FILE_ERROR", "error": str(exc)}, indent=2))
            return 1

    if payment_sig:
        headers["PAYMENT-SIGNATURE"] = payment_sig

    status, body, response_headers = request_json(
        f"{base}/api/marketplace/signals/{selected['signal_id']}/purchase",
        method="POST",
        headers=headers,
    )

    result: dict[str, Any] = {
        "agent": "PROMETHEUS_BUYER",
        "status": "PAYMENT_REQUIRED_OR_UNVERIFIED",
        "purchase_http_status": status,
        "purchase_response": body,
        "idempotency_key": idempotency_key,
    }

    payment_required = response_headers.get("PAYMENT-REQUIRED")
    if status == 402 and payment_required:
        try:
            parsed = json.loads(payment_required)
            result["payment_requirements"] = parsed
            result["payment_instructions"] = "To complete purchase, sign a payment payload for the listed amount and retry with PAYMENT-SIGNATURE header"
        except Exception:
            result["payment_requirements_raw"] = payment_required

    if status == 200:
        passport = body.get("passport", {})
        result["verified_hashes"] = {"signal_hash": passport.get("signal_hash"), "snapshot_hash": passport.get("snapshot_hash"), "quant_hash": passport.get("quant_hash")}
        result["status"] = "DELIVERED"
        result["passport"] = passport

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if status in {200, 402} else 1


if __name__ == "__main__":
    sys.exit(main())