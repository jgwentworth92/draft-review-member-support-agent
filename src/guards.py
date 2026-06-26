from __future__ import annotations

DEFAULT_INJECTION_PATTERNS: list[str] = [
    r"ignore (all |any )?(previous|prior|above) instructions",
    r"disregard (the |all )?(previous|prior|above)",
    r"you are now",
    r"new instructions",
    r"system prompt",
    r"reveal (your|the) (instructions|prompt|system)",
    r"print (your|the) (instructions|prompt)",
    r"jailbreak",
    r"pretend (to be|you are)",
    r"override (the |your )?(rules|instructions)",
]

DEFAULT_CREDENTIAL_PATTERNS: list[str] = [
    "full_card_number",
    "pin",
    "password",
    "cvv",
    "ssn",
    "full_account_number",
    "long_digit_sequence",
]

import re

_CREDENTIAL_RULES = [
    ("pin", r"\bpin\b"),
    ("password", r"\bpassword\b"),
    ("cvv", r"\bcvv\b|security code"),
    ("ssn", r"\bssn\b|social security number"),
    ("full_account_number", r"full account number"),
    ("long_digit_sequence", r"\b\d{13,}\b"),
]


def scan_input(text: str, patterns: list[str] | None = None) -> list[str]:
    pats = patterns if patterns is not None else DEFAULT_INJECTION_PATTERNS
    return [p for p in pats if re.search(p, text, re.IGNORECASE)]


def scan_output(text: str, patterns: list[str] | None = None) -> list[str]:
    """Return credential-violation labels found in an outgoing draft.

    `patterns` (when provided) is a list of allowed label names to check; the
    detection logic per label is fixed. Defaults to DEFAULT_CREDENTIAL_PATTERNS.
    """
    allowed = set(patterns if patterns is not None else DEFAULT_CREDENTIAL_PATTERNS)
    lowered = text.lower()
    findings: list[str] = []

    for label, pat in _CREDENTIAL_RULES:
        if label in allowed and re.search(pat, lowered):
            findings.append(label)

    if "full_card_number" in allowed:
        if re.search(r"full card number", lowered):
            findings.append("full_card_number")
        elif re.search(r"card number", lowered) and not re.search(r"last (4|four)", lowered):
            findings.append("full_card_number")

    return sorted(set(findings))
