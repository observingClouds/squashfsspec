"""Tests for the test infrastructure itself."""

# Third-party
import pytest

# First-party
from tests.conftest import REQUIRE_MKSQUASHFS_ENV, _missing_mksquashfs


def test_missing_mksquashfs_skips_by_default(monkeypatch):
    monkeypatch.delenv(REQUIRE_MKSQUASHFS_ENV, raising=False)
    with pytest.raises(pytest.skip.Exception, match="mksquashfs not found"):
        _missing_mksquashfs()


def test_missing_mksquashfs_fails_when_required(monkeypatch):
    monkeypatch.setenv(REQUIRE_MKSQUASHFS_ENV, "1")
    with pytest.raises(pytest.fail.Exception, match=REQUIRE_MKSQUASHFS_ENV):
        _missing_mksquashfs()
