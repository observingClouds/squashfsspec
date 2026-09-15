# Standard library
import pathlib
import shutil
import subprocess
from typing import Callable

# Third-party
import pytest


@pytest.fixture
def make_squashfs(tmp_path) -> Callable[[pathlib.Path, str], str]:
    """Return a callable that packs a directory into a SquashFS image.

    Input (of the returned callable):
    - source: directory whose contents become the image root.
    - name: file name of the image inside ``tmp_path``.

    Output:
    - Path to the created image as ``str``.

    The test is skipped when ``mksquashfs`` is not installed. A failing
    ``mksquashfs`` invocation is a test error, not a skip.
    """

    def _make(source: pathlib.Path, name: str = "image.squash") -> str:
        if shutil.which("mksquashfs") is None:
            pytest.skip("mksquashfs not found")
        dest = tmp_path / name
        subprocess.run(
            ["mksquashfs", str(source), str(dest), "-noappend"],
            check=True,
            capture_output=True,
        )
        return str(dest)

    return _make
