"""Tests for the test infrastructure itself."""

# Standard library
import shutil

# Third-party
import pytest


def test_missing_mksquashfs_fails_instead_of_skipping(
    make_squashfs, tmp_path, monkeypatch
):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(pytest.fail.Exception, match="mksquashfs not found"):
        make_squashfs(tmp_path)
