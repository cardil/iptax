"""Shared fixtures and utilities for CLI tests."""

import re

import pytest

# Regex to strip ANSI escape codes
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return ANSI_ESCAPE.sub("", text)


@pytest.fixture
def ansi_stripper():
    """Return the strip_ansi function as a fixture."""
    return strip_ansi
