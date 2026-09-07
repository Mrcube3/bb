from __future__ import annotations

from typing import Any

from .models import QuantPacket, Signal


class EvidenceError(ValueError):
    pass


class EvidenceValidator:
    """Validates that every factual claim in a signal cites existing evidence."""

    def validate(self, signal: Signal, quant: QuantPacket) -> None:
        if not signal.evidence_keys:
            raise EvidenceError("signal has no evidence_keys")

        supported = set(quant.evidence.keys())
        missing = [key for key in signal.evidence_keys if key not in supported]

        if missing:
            raise EvidenceError(
                f"UNSUPPORTED_CLAIM: evidence keys not present in quant packet: {missing}"
            )

        for key in signal.evidence_keys:
            if not key:
                raise EvidenceError("empty evidence key not allowed")
            if key not in quant.evidence:
                raise EvidenceError(f"UNSUPPORTED_CLAIM: referenced evidence key '{key}' does not exist")

        if signal.entry_reference <= 0:
            raise EvidenceError("entry_reference must be positive")
        if signal.invalidation <= 0:
            raise EvidenceError("invalidation must be positive")
        if not (0 <= signal.confidence <= 1):
            raise EvidenceError("confidence must be between 0 and 1")
        if not signal.thesis.strip():
            raise EvidenceError("thesis must not be empty")
        if not signal.risk_factors:
            raise EvidenceError("risk_factors must not be empty")

    def validate_claim(self, claim: str, quant: QuantPacket) -> list[str]:
        """Extract and validate evidence key references from a claim string."""
        imported = [
            word.strip("'\"").lower()
            for word in claim.split()
            if "_" in word and not word.startswith(("-", "+", "="))
        ]
        valid: set[str] = set(quant.evidence.keys())
        unsupported = [key for key in imported if key not in valid]
        if unsupported:
            raise EvidenceError(f"UNSUPPORTED_CLAIM: claim references non-existent evidence keys {unsupported}")
        return imported