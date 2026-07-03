from __future__ import annotations

import re

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

_CREDENTIAL_RULES = [
    ("pin", r"\bpin\b"),
    ("password", r"\bpassword\b"),
    ("cvv", r"\bcvv\b|security code"),
    ("ssn", r"\bssn\b|social security number"),
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

    # Card/account number rules. The strong match (an explicit full-number
    # qualifier) is never suppressed; the bare-phrase rule is suppressed only
    # by a "last 4" qualifier in the SAME sentence — a document-wide check let
    # "reply with your entire card number; we have the last 4 on file" through.
    sentences = re.split(r"[.!?\n]", lowered)
    for label, noun in (("full_card_number", "card"), ("full_account_number", "account")):
        if label not in allowed:
            continue
        if re.search(rf"\b(full|complete|entire|whole)\s+{noun}\s+number", lowered):
            findings.append(label)
        elif any(
            re.search(rf"{noun} number", s) and not re.search(r"last (4|four)", s)
            for s in sentences
        ):
            findings.append(label)

    return sorted(set(findings))
