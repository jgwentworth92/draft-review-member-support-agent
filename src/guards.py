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
_REQUEST_VERBS = (
    r"\b(share|provide|send|confirm|reply\s+with|respond\s+with|submit|enter|"
    r"give|tell|type|verify|include|key\s+in)\b"
)

# Negation handling, two scoped rules (a whole-sentence negation search would
# let one planted "not" whitelist a genuine request later in the sentence):
# - _NEGATION_NEAR: negation within two words of the request verb
#   ("do not share", "you shouldn't share"). Text is apostrophe-normalized
#   before matching, so the generic \w+n't covers shouldn't/doesn't/wouldn't.
# - _NEGATED_ASK: a negated ask/request verb suppresses the rest of the
#   sentence ("we wouldn't ask you to confirm your password").
_NEG = r"(?:\b(?:never|not|cannot|won'?t|don'?t|can'?t)\b|\b\w+n't\b)"
_NEGATION_NEAR = re.compile(rf"{_NEG}\W+(?:\w+\W+){{0,2}}$")
_NEGATED_ASK = re.compile(rf"{_NEG}\W+(?:\w+\W+){{0,2}}\b(?:ask\w*|request\w*|requir\w*|need\w*)\b")

# label -> credential-noun alternation; flagged only in request context.
_REQUEST_SHAPED_RULES = [
    ("pin", r"\bpin\b|personal identification number"),
    ("password", r"\bpassword\b|\bpasscode\b"),
    ("cvv", r"\bcvv2?\b|\bcvc\b|card verification (value|code)|security code"),
    ("ssn", r"\bssn\b|social security (number|#)"),
]

# Passive requests carry no request verb ("your PIN is required to proceed").
# The is/are/will-be + required/needed adjacency keeps negated forms
# ("is not required", "will never be needed") from matching.
_PASSIVE_REQUEST = r"[^.!?;\n]*\b(?:is|are|will\s+be)\s+(?:required|needed)\b"

# Presence-based, NOT request-shaped: digits (plain, spaced, or dashed) in an
# outgoing draft are the leak itself, regardless of verb. No upper bound -
# a 20+ digit run must still flag.
_LONG_DIGIT_SEQUENCE = re.compile(r"\b(?:\d[ -]?){12,}\d\b")


def _sentence_requests(sentence: str, noun_pattern: str) -> bool:
    """True when this sentence requests the credential: a non-negated request
    verb with the noun present anywhere in the sentence (covers noun-first
    phrasings like "your PIN, please send it"), or a passive required-form."""
    if re.search(noun_pattern, sentence):
        for verb in re.finditer(_REQUEST_VERBS, sentence):
            prefix = sentence[: verb.start()]
            if _NEGATION_NEAR.search(prefix) or _NEGATED_ASK.search(prefix):
                continue
            return True
    return bool(re.search(rf"(?:{noun_pattern}){_PASSIVE_REQUEST}", sentence))


def scan_input(text: str, patterns: list[str] | None = None) -> list[str]:
    pats = patterns if patterns is not None else DEFAULT_INJECTION_PATTERNS
    return [p for p in pats if re.search(p, text, re.IGNORECASE)]


def scan_output(text: str, patterns: list[str] | None = None) -> list[str]:
    """Return credential-violation labels found in an outgoing draft.

    `patterns` (when provided) is a list of allowed label names to check; the
    detection logic per label is fixed. Defaults to DEFAULT_CREDENTIAL_PATTERNS.
    """
    allowed = set(patterns if patterns is not None else DEFAULT_CREDENTIAL_PATTERNS)
    # Normalize typographic apostrophes so contraction-aware rules hold.
    lowered = text.lower().replace("’", "'")
    findings: list[str] = []
    # ';' is a sentence boundary here: the P1 5.3 exploit joined the request
    # and the suppressing "last 4" clause with a semicolon.
    sentences = re.split(r"[.!?;\n]", lowered)

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
