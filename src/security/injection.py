"""Screens stakeholder text for prompt-injection attempts.

Stakeholder documents are untrusted data. Anything that reads like an instruction to
the model is replaced with a visible marker (so it can never act as an instruction) and
reported, and the rest of the document is still analysed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

QUARANTINE_MARKER = "[REMOVED: possible prompt-injection text]"

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("override-instructions", re.compile(r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b(?:instructions?|prompts?|rules?|guidelines?)\b", re.I)),
    ("role-hijack", re.compile(r"\b(?:you are now|from now on you|act as (?:an? )?(?:different|new|unrestricted)|pretend (?:to be|you are))\b", re.I)),
    ("prompt-exfiltration", re.compile(r"\b(?:reveal|print|show|repeat|output)\b[^.\n]{0,30}\b(?:system prompt|your instructions|hidden prompt|initial prompt)\b", re.I)),
    ("chat-template-token", re.compile(r"<\|?(?:im_start|im_end|system|assistant|endoftext)\|?>|\[/?INST\]|<<SYS>>", re.I)),
    ("fake-system-block", re.compile(r"^\s*(?:#{1,3}\s*)?(?:system|developer)\s*(?:message|prompt|instruction)s?\s*:", re.I | re.M)),
    ("approval-bypass", re.compile(r"\b(?:mark|set|treat)\b[^.\n]{0,40}\b(?:as )?(?:approved|compliant|passed)\b[^.\n]{0,30}\b(?:without|skip|regardless)\b", re.I)),
]


@dataclass(frozen=True)
class InjectionFinding:
    pattern: str
    snippet: str


def screen(text: str) -> tuple[str, list[InjectionFinding]]:
    """Returns (text with offending sentences replaced by a marker, findings)."""
    findings: list[InjectionFinding] = []
    cleaned = text
    for name, pattern in _PATTERNS:
        def repl(m: re.Match[str], name: str = name) -> str:
            findings.append(InjectionFinding(name, m.group(0).strip()[:160]))
            return QUARANTINE_MARKER

        cleaned = pattern.sub(repl, cleaned)
    return cleaned, findings
