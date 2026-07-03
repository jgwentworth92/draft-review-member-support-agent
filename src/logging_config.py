"""Logging configuration for the application entrypoints.

Library modules (e.g. `src.graph`) only ever call `logging.getLogger(__name__)`
and emit records — they never configure handlers. The entrypoint (`src.api`
FastAPI app) calls `configure_logging()` once at startup so those records
actually get emitted.
"""

from __future__ import annotations

import logging
import os

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str | int | None = None) -> None:
    """Configure root logging once. Level defaults to the LOG_LEVEL env var, else INFO.

    Uses `logging.basicConfig`, which is a no-op if the root logger already has
    handlers (e.g. when running under uvicorn), so calling this is always safe.
    The `src` package logger's level is set explicitly so our records are emitted
    even when another runner owns the root handlers.
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")
    if isinstance(level, str):
        resolved = logging.getLevelNamesMapping().get(level.upper())
        if resolved is None:
            # An env typo must not prevent boot; fall back loudly to INFO.
            resolved = logging.INFO
            logging.getLogger(__name__).warning(
                "Invalid LOG_LEVEL %r; falling back to INFO", level
            )
        level = resolved
    logging.basicConfig(level=level, format=_DEFAULT_FORMAT)
    logging.getLogger("src").setLevel(level)
