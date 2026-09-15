# Standard library
import os
import pathlib
import shutil
import subprocess
from typing import Callable

# Third-party
import pytest

# Set to a non-empty value to turn a missing ``mksquashfs`` into a test
# failure instead of a skip. CI sets it so that a broken tool install
# cannot silently skip the whole suite.
REQUIRE_MKSQUASHFS_ENV = "SQUASHFSSPEC_REQUIRE_MKSQUASHFS"


def _missing_mksquashfs() -> None:
    message = "mksquashfs not found"
    if os.environ.get(REQUIRE_MKSQUASHFS_ENV):
        pytest.fail(
            f"{message}, but {REQUIRE_MKSQUASHFS_ENV} is set so skipping "
            "is not allowed"
        )
    pytest.skip(message)


@pytest.fixture
def make_squashfs(tmp_path) -> Callable[[pathlib.Path, str], str]:
    """Return a callable that packs a directory into a SquashFS image.

    Input (of the returned callable):
    - source: directory whose contents become the image root.
    - name: file name of the image inside ``tmp_path``.

    Output:
    - Path to the created image as ``str``.

    The test is skipped when ``mksquashfs`` is not installed, unless
    ``SQUASHFSSPEC_REQUIRE_MKSQUASHFS`` is set, in which case it fails. A
    failing ``mksquashfs`` invocation is always a test error, not a skip.
    """

    def _make(source: pathlib.Path, name: str = "image.squash") -> str:
        if shutil.which("mksquashfs") is None:
            _missing_mksquashfs()
        dest = tmp_path / name
        subprocess.run(
            ["mksquashfs", str(source), str(dest), "-noappend"],
            check=True,
            capture_output=True,
        )
        return str(dest)

    return _make
