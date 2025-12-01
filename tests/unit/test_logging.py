"""Unit tests for iptax.utils.logging module."""

import logging
from pathlib import Path

from iptax.utils.logging import LOG_FORMAT, RelativePathFormatter, setup_logging


class TestRelativePathFormatter:
    """Test RelativePathFormatter class."""

    def test_init_default_base_path(self):
        """Test formatter initializes with default base path."""
        formatter = RelativePathFormatter(LOG_FORMAT)
        assert formatter.base_path == str(Path.cwd())

    def test_init_custom_base_path(self):
        """Test formatter initializes with custom base path."""
        custom_path = "/custom/base/path"
        formatter = RelativePathFormatter(LOG_FORMAT, base_path=custom_path)
        assert formatter.base_path == custom_path

    def test_format_converts_to_relative_path(self, tmp_path: Path):
        """Test format converts absolute path to relative."""
        formatter = RelativePathFormatter(LOG_FORMAT, base_path=str(tmp_path))

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=str(tmp_path / "subdir" / "test.py"),
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        assert "subdir" in formatted or "test.py" in formatted

    def test_format_handles_missing_pathname(self):
        """Test format handles record with empty pathname."""
        formatter = RelativePathFormatter(LOG_FORMAT)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        assert "Test message" in formatted


class TestSetupLogging:
    """Test setup_logging function."""

    def test_setup_logging_creates_file_handler(self, tmp_path: Path):
        """Test setup_logging creates a file handler."""
        log_file = tmp_path / "test.log"

        setup_logging(log_file)

        # Verify file was created
        assert log_file.exists()

        # Cleanup: remove handlers from root logger
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()

    def test_setup_logging_with_extra_handlers(self, tmp_path: Path):
        """Test setup_logging adds extra handlers."""
        log_file = tmp_path / "test.log"
        extra_handler = logging.StreamHandler()

        setup_logging(log_file, extra_handlers=[extra_handler])

        root_logger = logging.getLogger()
        try:
            # Verify the extra handler was attached
            assert extra_handler in root_logger.handlers
        finally:
            # Cleanup: remove handlers from root logger
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
                handler.close()

    def test_setup_logging_sets_level(self, tmp_path: Path):
        """Test setup_logging sets the correct level."""
        log_file = tmp_path / "test.log"

        setup_logging(log_file, level=logging.WARNING)

        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING

        # Cleanup: remove handlers from root logger
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
