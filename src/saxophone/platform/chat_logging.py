"""Terminal and daily-file configuration for safe chat logs."""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
import sys
from typing import TextIO

from saxophone.agent.logging import CHAT_LOGGER_NAME


def configure_chat_logging(
    *,
    log_directory: Path = Path("logs"),
    stream: TextIO | None = None,
    level: str | int = "INFO",
) -> logging.Logger:
    """Configure one idempotent console handler and one daily file handler."""

    if not isinstance(log_directory, Path):
        raise TypeError("log_directory must be a Path")
    logger = logging.getLogger(CHAT_LOGGER_NAME)
    resolved_level = _resolve_level(level)
    logger.setLevel(resolved_level)
    logger.propagate = False
    target_stream = stream or sys.stdout

    if not _has_handler(logger, "console", target_stream=target_stream):
        handler = logging.StreamHandler(target_stream)
        handler.setLevel(resolved_level)
        handler._saxophone_chat_kind = "console"  # type: ignore[attr-defined]
        handler.setFormatter(_ChatFormatter())
        logger.addHandler(handler)

    if not _has_handler(logger, "daily_file", log_directory=log_directory):
        handler = _DailyChatFileHandler(log_directory)
        handler.setLevel(resolved_level)
        handler._saxophone_chat_kind = "daily_file"  # type: ignore[attr-defined]
        logger.addHandler(handler)
    return logger


class _ChatFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "chat_event", None)
        if not isinstance(event, dict):
            return super().format(record)
        fields = [
            ("timestamp", datetime.now().astimezone().isoformat()),
            ("level", record.levelname),
        ]
        fields.extend((str(key), value) for key, value in event.items())
        return " | ".join(f"{key}={value}" for key, value in fields)


class _DailyChatFileHandler(logging.Handler):
    def __init__(self, log_directory: Path) -> None:
        super().__init__(level=logging.INFO)
        self.log_directory = log_directory

    def emit(self, record: logging.LogRecord) -> None:
        event = getattr(record, "chat_event", None)
        if not isinstance(event, dict):
            return
        try:
            self.log_directory.mkdir(parents=True, exist_ok=True)
            target = self.log_directory / f"{datetime.now().astimezone().date().isoformat()}.log"
            with target.open("a", encoding="utf-8", newline="\n") as output:
                output.write(_ChatFormatter().format(record))
                output.write("\n")
        except Exception:
            self.handleError(record)


def _has_handler(
    logger: logging.Logger,
    kind: str,
    *,
    target_stream: TextIO | None = None,
    log_directory: Path | None = None,
) -> bool:
    for handler in logger.handlers:
        if getattr(handler, "_saxophone_chat_kind", None) != kind:
            continue
        if kind == "console" and getattr(handler, "stream", None) is target_stream:
            return True
        if kind == "daily_file" and getattr(handler, "log_directory", None) == log_directory:
            return True
    return False


def _resolve_level(level: str | int) -> int:
    if isinstance(level, int) and not isinstance(level, bool):
        return level
    if isinstance(level, str):
        resolved = logging.getLevelName(level.upper())
        if isinstance(resolved, int):
            return resolved
    raise ValueError("level must be a logging level")


__all__ = ["configure_chat_logging"]
