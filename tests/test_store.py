# Standard library
import os
import subprocess

# Third-party
import numpy as np
import pytest
import xarray as xr

# First-party
from squashfsspec import SquashFSFileSystem, SquashFSStore


def _mksquashfs_available():
    """Return True when mksquashfs is on PATH."""
    try:
        subprocess.run(
            ["mksquashfs", "-version"],
            check=True,
            capture_output=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


pytestmark = pytest.mark.skipif(
    not _mksquashfs_available(),
    reason="mksquashfs not available",
)


# ---------------------------------------------------------------------------
# Basic write / read-back round-trip
# ---------------------------------------------------------------------------


def test_basic_write_read_roundtrip(tmp_path):
    """A dataset written via SquashFSStore can be read back."""
    squash_path = str(tmp_path / "basic.squash")

    ds_orig = xr.Dataset(
        {"temperature": (("x", "y"), np.arange(12, dtype=float).reshape(3, 4))},
        coords={"x": [1, 2, 3], "y": [10, 20, 30, 40]},
    )

    with SquashFSStore(squash_path) as store:
        ds_orig.to_zarr(store, consolidated=False)

    assert os.path.exists(squash_path), "SquashFS image was not created"

    ds_read = xr.open_dataset(
        "squashfs:///",
        engine="zarr",
        consolidated=False,
        backend_kwargs={"storage_options": {"fo": squash_path}},
    )
    xr.testing.assert_equal(ds_orig, ds_read)


def test_image_created_on_context_exit(tmp_path):
    """The SquashFS image is produced when the context manager exits."""
    squash_path = str(tmp_path / "context.squash")

    ds = xr.Dataset({"v": ("x", np.arange(4, dtype=float))})

    assert not os.path.exists(squash_path)
    with SquashFSStore(squash_path) as store:
        ds.to_zarr(store, consolidated=False)
        # Image should not exist yet — still inside the context.
        assert not os.path.exists(squash_path)

    # Image should exist now.
    assert os.path.exists(squash_path)


def test_discard_no_image(tmp_path):
    """discard() abandons staged files without creating a SquashFS image."""
    squash_path = str(tmp_path / "discarded.squash")

    ds = xr.Dataset({"v": ("x", np.arange(4, dtype=float))})

    store = SquashFSStore(squash_path)
    ds.to_zarr(store, consolidated=False)
    store.discard()

    assert not os.path.exists(squash_path)


def test_exception_inside_context_triggers_discard(tmp_path):
    """An exception inside the with-block triggers discard, not commit."""
    squash_path = str(tmp_path / "exc.squash")

    ds = xr.Dataset({"v": ("x", np.arange(4, dtype=float))})

    with pytest.raises(RuntimeError):
        with SquashFSStore(squash_path) as store:
            ds.to_zarr(store, consolidated=False)
            raise RuntimeError("simulated error")

    assert not os.path.exists(squash_path)


# ---------------------------------------------------------------------------
# with_prefix — multiple datasets in one archive
# ---------------------------------------------------------------------------


def test_with_prefix_multiple_datasets(tmp_path):
    """Multiple zarr datasets can be staged under different prefixes."""
    squash_path = str(tmp_path / "multi.squash")

    ds1 = xr.Dataset({"a": ("x", np.arange(5, dtype=float))})
    ds2 = xr.Dataset({"b": ("y", np.arange(3, dtype=float))})

    with SquashFSStore(squash_path) as store:
        ds1.to_zarr(store.with_prefix("ds1.zarr"), consolidated=False)
        ds2.to_zarr(store.with_prefix("ds2.zarr"), consolidated=False)

    rfs = SquashFSFileSystem(squash_path)
    root_entries = rfs.ls("/", detail=False)
    assert any("ds1.zarr" in e for e in root_entries)
    assert any("ds2.zarr" in e for e in root_entries)
    rfs.close()


def test_with_prefix_read_back(tmp_path):
    """Datasets written via with_prefix are readable by their sub-path."""
    squash_path = str(tmp_path / "multi_read.squash")

    ds1 = xr.Dataset({"a": ("x", np.arange(5, dtype=float))})
    ds2 = xr.Dataset({"b": ("y", np.arange(3, dtype=float))})

    with SquashFSStore(squash_path) as store:
        ds1.to_zarr(store.with_prefix("ds1.zarr"), consolidated=False)
        ds2.to_zarr(store.with_prefix("ds2.zarr"), consolidated=False)

    ds1_read = xr.open_dataset(
        "squashfs:///ds1.zarr",
        engine="zarr",
        consolidated=False,
        backend_kwargs={"storage_options": {"fo": squash_path}},
    )
    ds2_read = xr.open_dataset(
        "squashfs:///ds2.zarr",
        engine="zarr",
        consolidated=False,
        backend_kwargs={"storage_options": {"fo": squash_path}},
    )
    xr.testing.assert_equal(ds1, ds1_read)
    xr.testing.assert_equal(ds2, ds2_read)


# ---------------------------------------------------------------------------
# Staging-area inspection
# ---------------------------------------------------------------------------


def test_staging_dir_removed_after_commit(tmp_path):
    """The staging directory is cleaned up after a successful commit."""
    squash_path = str(tmp_path / "cleanup.squash")

    ds = xr.Dataset({"v": ("x", np.arange(4, dtype=float))})

    with SquashFSStore(squash_path) as store:
        staging = store._staging_dir
        ds.to_zarr(store, consolidated=False)

    assert not os.path.exists(staging), "Staging directory was not removed after commit"


def test_staging_dir_removed_after_discard(tmp_path):
    """The staging directory is cleaned up after discard()."""
    squash_path = str(tmp_path / "cleanup_discard.squash")

    ds = xr.Dataset({"v": ("x", np.arange(4, dtype=float))})

    store = SquashFSStore(squash_path)
    staging = store._staging_dir
    ds.to_zarr(store, consolidated=False)
    store.discard()

    assert not os.path.exists(staging), "Staging directory was not removed after discard"
