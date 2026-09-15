# Standard library
import pathlib
import re

# Third-party
import numpy as np
import pytest
import xarray as xr

README = pathlib.Path(__file__).parent.parent / "README.md"


def _get_code_block(readme: pathlib.Path, pattern: str) -> str:
    """Return the first Python code block in *readme* that contains *pattern*.

    Raises a pytest failure if no matching block is found so that a missing or
    renamed example in the README surfaces as an explicit test error.
    """
    blocks = re.findall(r"```python\n(.*?)```", readme.read_text(), re.DOTALL)
    try:
        return next(b for b in blocks if pattern in b)
    except StopIteration:
        pytest.fail(
            f"No Python code block matching {pattern!r} found in {readme}. "
            "The README example may have been removed or renamed."
        )


@pytest.fixture
def squashfs_file(tmp_path, make_squashfs):
    """SquashFS file with a nested text file for the README basic usage
    example."""
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    (test_dir / "some").mkdir()
    (test_dir / "some" / "file.txt").write_text("Hello, SquashFS!")

    return make_squashfs(test_dir, "test.squash")


@pytest.fixture
def zarr_squashfs_file(tmp_path, make_squashfs):
    """SquashFS file with a Zarr store at root for the README xarray example."""
    zarr_path = tmp_path / "data.zarr"

    ds = xr.Dataset(
        {"temperature": (("x", "y"), np.random.rand(4, 5))},
        coords={"x": [10, 20, 30, 40], "y": np.arange(5)},
    )
    ds.to_zarr(str(zarr_path))

    return make_squashfs(zarr_path, "data.squash")


@pytest.fixture
def multi_zarr_squashfs_file(tmp_path, make_squashfs):
    """SquashFS file with multiple Zarr v2 stores for the README multiple
    datasets example."""
    base_dir = tmp_path / "data"
    base_dir.mkdir()

    ds1 = xr.Dataset(
        {"temperature": (("x", "y"), np.random.rand(4, 5))},
        coords={"x": [10, 20, 30, 40], "y": np.arange(5)},
    )
    ds2 = xr.Dataset(
        {"pressure": (("a", "b"), np.random.rand(3, 3))},
        coords={"a": [1, 2, 3], "b": [1, 2, 3]},
    )

    # Zarr v2 writes consolidated metadata (.zmetadata) required by
    # consolidated=True.
    ds1.to_zarr(str(base_dir / "dataset1.zarr"), zarr_format=2)
    ds2.to_zarr(str(base_dir / "dataset2.zarr"), zarr_format=2)

    return make_squashfs(base_dir, "multidata.squash")


def test_readme_basic_usage(squashfs_file):
    """README: Basic Usage with fsspec — code extracted directly from
    README.md."""
    code = _get_code_block(README, 'fsspec.filesystem("squashfs"')
    code = code.replace('"path/to/your.squash"', repr(squashfs_file))
    ns: dict = {}
    exec(code, ns)  # noqa: S102
    assert ns["fs"].exists("some/file.txt")


def test_readme_xarray_zarr(zarr_squashfs_file):
    """README: Working with Xarray and Zarr — code extracted directly from
    README.md."""
    code = _get_code_block(README, '"squashfs:///"')
    code = code.replace('"path/to/data.squash"', repr(zarr_squashfs_file))
    ns: dict = {}
    exec(code, ns)  # noqa: S102
    assert "temperature" in ns["ds"].variables


def test_readme_multiple_datasets(multi_zarr_squashfs_file):
    """README: Accessing Multiple Datasets — code extracted directly from
    README.md."""
    code = _get_code_block(README, "dataset_path}::{squashfs_path}")
    code = code.replace(
        '"path/to/multidata.squash"', repr(multi_zarr_squashfs_file)
    )
    code = code.replace(
        '"path/in/squashfs/file/to/dataset.zarr"', '"dataset1.zarr"'
    )
    ns: dict = {}
    exec(code, ns)  # noqa: S102
    assert "temperature" in ns["ds"].variables
