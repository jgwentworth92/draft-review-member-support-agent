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
