from __future__ import annotations
import logging
import os
from langgraph.types import RetryPolicy
from src.config import RetryConfig

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def retry_policy(cfg: RetryConfig | None) -> RetryPolicy | None:
    if cfg is None:
        return None
    return RetryPolicy(
        max_attempts=cfg.max_attempts,
        backoff_factor=cfg.backoff_factor,
        initial_interval=cfg.initial_interval,
        max_interval=cfg.max_interval,
        jitter=cfg.jitter,
    )


def configure_logging(level: str | int | None = None) -> None:
    """Configure root logging once. Level defaults to the LOG_LEVEL env var, else INFO.

    Uses `logging.basicConfig`, which is a no-op if the root logger already has
    handlers (e.g. when running under uvicorn), so calling this is always safe.
    The `src` package logger's level is set explicitly so our records are emitted
    even when another runner owns the root handlers.
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")
    logging.basicConfig(level=level, format=_DEFAULT_FORMAT)
    logging.getLogger("src").setLevel(level)
