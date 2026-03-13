"""
Centralised logging configuration for the SDG extractor.

Uses Python's stdlib logging with optional Rich handler for coloured
console output. All modules should import the logger from here via:

    from app.utils.logger import get_logger
    logger = get_logger(__name__)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

try:
    from rich.logging import RichHandler
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False

_configured = False


def configure_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Configure root logger. Call once at application startup.

    Args:
        level:    Logging level string (DEBUG | INFO | WARNING | ERROR).
        log_file: Optional path to write logs to disk as well as stdout.
    """
    global _configured
    if _configured:
        return

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handlers: list[logging.Handler] = []

    if _RICH_AVAILABLE:
        handlers.append(
            RichHandler(
                level=numeric_level,
                rich_tracebacks=True,
                show_path=False,
                markup=True,
            )
        )
    else:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(numeric_level)
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        stream_handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
        handlers.append(stream_handler)

    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(numeric_level)
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        file_handler.setFormatter(logging.Formatter(fmt))
        handlers.append(file_handler)

    logging.basicConfig(level=numeric_level, handlers=handlers, force=True)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. configure_logging() should have been called first."""
    return logging.getLogger(name)
