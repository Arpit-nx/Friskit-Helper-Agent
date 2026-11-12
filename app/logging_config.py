from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> None:
    """Write application logs to a rotating file in the project logs folder."""
    app_logger = logging.getLogger("rag")
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False

    # Avoid adding duplicate handlers when the app is reloaded in development.
    if any(getattr(handler, "_rag_file_handler", False) for handler in app_logger.handlers):
        return

    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler._rag_file_handler = True
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    ))
    app_logger.addHandler(file_handler)

