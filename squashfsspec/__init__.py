# Standard library
from importlib.metadata import PackageNotFoundError, version

# First-party
from squashfsspec.squashfsspec import OffsetWrapper, SquashFSFileSystem

try:
    __version__ = version("squashfsspec")
except PackageNotFoundError:  # pragma: no cover - source tree without install
    __version__ = "0+unknown"

__all__ = ["SquashFSFileSystem", "OffsetWrapper", "__version__"]
