"""Logging helpers."""

import logging
from typing import Optional

from rich.logging import RichHandler


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger configured with rich handler."""
    logger = logging.getLogger(name or "medparse")
    if not logger.handlers:
        handler = RichHandler(rich_tracebacks=True)
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
