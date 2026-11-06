"""Structured JSON logging with a per-run correlation id.

`run_id_var` holds the id of the run being processed. A filter copies it onto every log
record, so code never passes `run_id` by hand. Logs must never contain candidate emails or
message text: log ids, codes, counts and durations only.
"""
import contextvars
import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import IO, Any

run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id", default=None)

_HANDLER_MARK = "_cma_json_handler"
# Attributes every LogRecord has; anything else on a record came from `extra=`.
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "run_id"}


@contextmanager
def bind_run_id(run_id: str) -> Iterator[None]:
    """Make `run_id` appear on every log record inside the block, then restore the old value."""
    token = run_id_var.set(run_id)
    try:
        yield
    finally:
        run_id_var.reset(token)


class RunIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = run_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        run_id = getattr(record, "run_id", None)
        if run_id is not None:
            entry["run_id"] = run_id
        entry.update({k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO", stream: IO[str] | None = None) -> None:
    """Send all logs to one JSON handler on the root logger. Safe to call more than once."""
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, _HANDLER_MARK, False)]:
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stderr)
    setattr(handler, _HANDLER_MARK, True)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RunIdFilter())
    root.addHandler(handler)
    root.setLevel(level)
