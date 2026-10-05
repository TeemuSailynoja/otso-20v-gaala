"""Shared paths and fixture loading for the ultiorg test suite."""

from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES = TESTS_DIR / "fixtures"
GOLDEN = TESTS_DIR / "golden"


def read_fixture(name: str) -> str:
    """Read a committed fixture verbatim.

    Fixtures are archived Ultiorganizer pages. They are read with
    errors="replace" because a few archived pages are not valid UTF-8.
    """
    path = FIXTURES / name
    if not path.exists():
        raise FileNotFoundError(f"missing fixture {path}; run tests/regenerate_golden.py")
    return path.read_text(encoding="utf-8", errors="replace")


@pytest.fixture
def fixture_text():
    return read_fixture
