"""The security gate every stakeholder input passes through before it is stored or analysed."""

from __future__ import annotations

from dataclasses import dataclass

from src.security.injection import screen
from src.security.pii import mask_pii


@dataclass
class GateResult:
    text: str
    pii_found: dict[str, int]
    injection: list[dict]


def secure_input(raw_text: str) -> GateResult:
    """Quarantines prompt-injection text, then masks PII. The raw text is not kept."""
    cleaned, findings = screen(raw_text)
    masked = mask_pii(cleaned)
    return GateResult(
        text=masked.text,
        pii_found=masked.found,
        injection=[{"pattern": f.pattern, "snippet": f.snippet} for f in findings],
    )
