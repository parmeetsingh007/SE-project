"""Detects and masks personal/financial identifiers before text goes anywhere else.

Applied to every input at the door: the model, the database and the exports only
ever see the masked text. Regex based, so it catches structured identifiers, not
free-text person names or addresses (a known, documented limitation).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class MaskResult:
    text: str
    found: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.found.values())


def _luhn_ok(digits: str) -> bool:
    total, flip = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if flip:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        flip = not flip
    return total % 10 == 0


# Order matters: longer / more specific identifiers first so a card number is not
# half-eaten by the phone pattern.
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,3})?\b")
_CARD = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
_AADHAAR = re.compile(r"(?<![\d-])[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?![\d-])")
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_PASSPORT = re.compile(r"\b(?:passport(?:\s*(?:no\.?|number|#))?[\s:]*)([A-Z]\d{7})\b", re.IGNORECASE)
_PHONE_IN = re.compile(r"(?<![\d-])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
_PHONE_US = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")
_DOB = re.compile(
    r"\b(?:dob|d\.o\.b\.?|date of birth|born on)[\s:]*"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


def mask_pii(text: str) -> MaskResult:
    """Replaces identifiers with stable placeholders like ``[AADHAAR_1]``."""
    found: dict[str, int] = {}
    counters: dict[str, int] = {}

    def placeholder(kind: str) -> str:
        counters[kind] = counters.get(kind, 0) + 1
        found[kind] = counters[kind]
        return f"[{kind}_{counters[kind]}]"

    def simple(pattern: re.Pattern[str], kind: str, text_in: str) -> str:
        return pattern.sub(lambda _m: placeholder(kind), text_in)

    def validated(pattern: re.Pattern[str], kind: str, text_in: str, check) -> str:
        def repl(m: re.Match[str]) -> str:
            digits = re.sub(r"\D", "", m.group(0))
            return placeholder(kind) if check(digits) else m.group(0)

        return pattern.sub(repl, text_in)

    out = text
    out = simple(_EMAIL, "EMAIL", out)
    out = simple(_IBAN, "IBAN", out)
    out = validated(_CARD, "CARD_NUMBER", out, lambda d: 13 <= len(d) <= 19 and _luhn_ok(d))
    out = validated(_AADHAAR, "AADHAAR", out, lambda d: len(d) == 12)
    out = simple(_PAN, "PAN", out)
    out = simple(_SSN, "SSN", out)
    out = _PASSPORT.sub(lambda m: m.group(0).replace(m.group(1), placeholder("PASSPORT")), out)
    out = _DOB.sub(lambda m: m.group(0).replace(m.group(1), placeholder("DOB")), out)
    out = simple(_PHONE_IN, "PHONE", out)
    out = simple(_PHONE_US, "PHONE", out)
    return MaskResult(text=out, found=found)
