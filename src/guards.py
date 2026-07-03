from __future__ import annotations

import re

# \s+ instead of literal spaces (whitespace/newline tricks), and alternations
# widened to cover "the/your/everything" phrasings. These are a screen, not a
# defense: the LLM checklist and human-gated terminal states are the backstop.
DEFAULT_INJECTION_PATTERNS: list[str] = [
    r"ignore\s+(all\s+|any\s+|the\s+|your\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(the\s+|all\s+|everything\s+)?(previous|prior|above)",
    r"you\s+are\s+now",
    r"new\s+instructions",
    r"system\s+prompt",
    r"reveal\s+(your|the)\s+(instructions|prompt|system)",
    r"print\s+(your|the)\s+(instructions|prompt)",
    r"jailbreak",
    r"pretend\s+(to\s+be|you\s+are)",
    r"override\s+(the\s+|your\s+)?(rules|instructions)",
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

# Request verbs that make a credential noun an actual request. "ask" is
# deliberately absent: "we will never ask for your PIN" is the compliant
# warning this request-shaping exists to stop flagging.
_REQUEST_VERBS = r"\b(share|provide|send|confirm|reply with|enter|give|tell|type|verify|include)\b"
_NEGATION = re.compile(r"\b(never|not|won'?t|don'?t|cannot|can'?t)\b")

# label -> credential-noun alternation; flagged only when a non-negated
# request verb precedes the noun within the same sentence.
_REQUEST_SHAPED_RULES = [
    ("pin", r"\bpin\b|personal identification number"),
    ("password", r"\bpassword\b|\bpasscode\b"),
    ("cvv", r"\bcvv2?\b|\bcvc\b|card verification (value|code)|security code"),
    ("ssn", r"\bssn\b|social security (number|#)"),
]

# Presence-based, NOT request-shaped: digits (plain, spaced, or dashed) in an
# outgoing draft are the leak itself, regardless of verb.
_LONG_DIGIT_SEQUENCE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")


def _sentence_requests(sentence: str, noun_pattern: str) -> bool:
    """True when a request verb precedes the credential noun in this sentence
    and no negation cue precedes the verb ("never share your PIN" is safe)."""
    for verb in re.finditer(_REQUEST_VERBS, sentence):
        if _NEGATION.search(sentence[: verb.start()]):
            continue
        if re.search(noun_pattern, sentence[verb.end():]):
            return True
    return False


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
    sentences = re.split(r"[.!?\n]", lowered)

    for label, noun_pat in _REQUEST_SHAPED_RULES:
        if label in allowed and any(_sentence_requests(s, noun_pat) for s in sentences):
            findings.append(label)

    if "long_digit_sequence" in allowed and _LONG_DIGIT_SEQUENCE.search(lowered):
        findings.append("long_digit_sequence")

    # Card/account number rules. The strong match (an explicit full-number
    # qualifier) is never suppressed; the bare-phrase rule is suppressed only
    # by a "last 4" qualifier in the SAME sentence — a document-wide check let
    # "reply with your entire card number; we have the last 4 on file" through.
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
