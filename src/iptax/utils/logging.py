"""Logging configuration utilities.

This module provides centralized logging setup with consistent formatting.
"""

import logging
import os
from collections.abc import Sequence
from pathlib import Path

# Common log format - levelname width 7 to fit "WARNING"
# %(relpath)s is a custom field added by RelativePathFormatter
LOG_FORMAT = "[%(levelname)7s] %(asctime)s (%(relpath)s:%(lineno)d) --- %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class RelativePathFormatter(logging.Formatter):
    """Formatter that converts absolute paths to relative module paths."""

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        base_path: str | None = None,
    ) -> None:
        """Initialize the formatter.

        Args:
            fmt: Log format string
            datefmt: Date format string
            base_path: Base path to make paths relative to (default: cwd)
        """
        super().__init__(fmt, datefmt)
        self.base_path = base_path or str(Path.cwd())

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with relative path."""
        # Convert absolute pathname to relative
        if record.pathname:
            try:
                relpath = os.path.relpath(record.pathname, self.base_path)
            except ValueError:
                # On Windows, relpath fails for different drives
                relpath = record.pathname
        else:
            relpath = record.filename or "unknown"

        # Add custom field to record
        record.relpath = relpath
        return super().format(record)


def setup_logging(
    log_file: Path,
    level: int = logging.DEBUG,
    extra_handlers: Sequence[logging.Handler] | None = None,
) -> None:
    """Setup logging with consistent format.

    Args:
        log_file: Path to log file (truncated on each run)
        level: Log level (default: DEBUG)
        extra_handlers: Additional handlers to add (e.g., StreamHandler for console)
    """
    formatter = RelativePathFormatter(LOG_FORMAT, LOG_DATE_FORMAT)

    handlers: list[logging.Handler] = [
        logging.FileHandler(log_file, mode="w"),
    ]
    if extra_handlers:
        handlers.extend(extra_handlers)

    # Apply formatter to all handlers
    for handler in handlers:
        handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in handlers:
        root_logger.addHandler(handler)
