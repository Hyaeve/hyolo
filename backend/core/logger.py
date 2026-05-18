from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _has_named_handler(logger: logging.Logger, handler_name: str) -> bool:
    return any(getattr(handler, "name", "") == handler_name for handler in logger.handlers)


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if not _has_named_handler(root_logger, "hyolo-console"):
        console_handler = logging.StreamHandler()
        console_handler.name = "hyolo-console"
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if not _has_named_handler(root_logger, "hyolo-file"):
        file_handler = RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        file_handler.name = "hyolo-file"
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
