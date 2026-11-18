"""Minimal structured (JSON line) logging configuration."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_RESERVED_LOG_RECORD_KEYS = {
    "args",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "msg",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
}

logger = logging.getLogger("mindvault")


class JsonLineFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_KEYS and key not in payload and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    """Send structured logs to stdout at the configured level."""

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLineFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
