# Standard library
import gc
import subprocess

# Third-party
import numpy as np
import pytest
import xarray as xr

# First-party
from squashfsspec import SquashFSFileSystem


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
# Basic file write / read-back round-trip
# ---------------------------------------------------------------------------


def test_inferred_write_mode(tmp_path):
    """Mode is inferred as write when the target path does not yet exist."""
    squash_path = str(tmp_path / "inferred.squash")

    # No mode= kwarg — should auto-detect write because file doesn't exist
    fs = SquashFSFileSystem(squash_path)
    assert fs._mode == "w", "Expected write mode to be inferred"
    with fs.open("/probe.txt", "wb") as f:
        f.write(b"inferred")
    fs.close()

    rfs = SquashFSFileSystem(squash_path)
    assert rfs._mode == "r", "Expected read mode after file exists"
    with rfs.open("probe.txt", "rb") as f:
        assert f.read() == b"inferred"
    rfs.close()


def test_explicit_write_mode(tmp_path):
    """Explicit mode='w' forces write mode even if the path does not exist."""
    squash_path = str(tmp_path / "explicit.squash")

    with SquashFSFileSystem(squash_path, mode="w") as fs:
        assert fs._mode == "w"
        with fs.open("/data.bin", "wb") as f:
            f.write(b"explicit")

    rfs = SquashFSFileSystem(squash_path)
    with rfs.open("data.bin", "rb") as f:
        assert f.read() == b"explicit"
    rfs.close()


def test_write_and_read_back(tmp_path):
    """Files written via SquashFSFileSystem (write mode) can be read back."""
    squash_path = str(tmp_path / "out.squash")

    with SquashFSFileSystem(squash_path) as wfs:
        wfs.mkdir("/subdir")
        with wfs.open("/hello.txt", "wb") as f:
            f.write(b"Hello, SquashFS!")
        with wfs.open("/subdir/nested.txt", "wb") as f:
            f.write(b"Nested content")

    # Read back using the read-only filesystem
    rfs = SquashFSFileSystem(squash_path)
    with rfs.open("hello.txt", "rb") as f:
        assert f.read() == b"Hello, SquashFS!"
    with rfs.open("subdir/nested.txt", "rb") as f:
        assert f.read() == b"Nested content"


def test_ls_staging(tmp_path):
    """ls() reflects files staged before commit."""
    squash_path = str(tmp_path / "ls_test.squash")

    wfs = SquashFSFileSystem(squash_path)
    try:
        wfs.mkdir("/mydir")
        with wfs.open("/mydir/a.txt", "wb") as f:
            f.write(b"a")
        with wfs.open("/mydir/b.txt", "wb") as f:
            f.write(b"b")

        names = wfs.ls("/mydir", detail=False)
        assert any("a.txt" in n for n in names)
        assert any("b.txt" in n for n in names)
    finally:
        wfs.close()


def test_exists_isfile_isdir(tmp_path):
    """exists / isfile / isdir reflect staging state."""
    squash_path = str(tmp_path / "meta_test.squash")

    wfs = SquashFSFileSystem(squash_path)
    try:
        wfs.mkdir("/d")
        with wfs.open("/d/f.bin", "wb") as f:
            f.write(b"\x00")

        assert wfs.exists("/d")
        assert wfs.isdir("/d")
        assert not wfs.isfile("/d")
        assert wfs.exists("/d/f.bin")
        assert wfs.isfile("/d/f.bin")
        assert not wfs.isdir("/d/f.bin")
        assert not wfs.exists("/nonexistent")
    finally:
        wfs.close()


def test_rm_file(tmp_path):
    """rm() removes a staged file."""
    squash_path = str(tmp_path / "rm_test.squash")

    wfs = SquashFSFileSystem(squash_path)
    try:
        with wfs.open("/to_delete.txt", "wb") as f:
            f.write(b"bye")
        assert wfs.exists("/to_delete.txt")
        wfs.rm("/to_delete.txt")
        assert not wfs.exists("/to_delete.txt")
    finally:
        wfs.close()


def test_rm_recursive(tmp_path):
    """rm(recursive=True) removes a staged directory tree."""
    squash_path = str(tmp_path / "rm_rec.squash")

    wfs = SquashFSFileSystem(squash_path)
    try:
        wfs.mkdir("/tree")
        with wfs.open("/tree/leaf.txt", "wb") as f:
            f.write(b"leaf")
        wfs.rm("/tree", recursive=True)
        assert not wfs.exists("/tree")
    finally:
        wfs.close()


def test_discard_does_not_write(tmp_path):
    """discard() abandons staged files; no SquashFS image is created."""
    squash_path = str(tmp_path / "discarded.squash")

    wfs = SquashFSFileSystem(squash_path)
    with wfs.open("/data.txt", "wb") as f:
        f.write(b"data")
    wfs.discard()

    import os

    assert not os.path.exists(squash_path)


def test_closed_raises(tmp_path):
    """Operations after close() raise ValueError."""
    squash_path = str(tmp_path / "closed.squash")

    wfs = SquashFSFileSystem(squash_path)
    wfs.close()

    with pytest.raises(ValueError, match="closed"):
        wfs.open("/x", "wb")


def test_context_manager_exception_discards(tmp_path):
    """An exception inside the with block triggers discard, not commit."""
    import os

    squash_path = str(tmp_path / "exc.squash")

    with pytest.raises(RuntimeError):
        with SquashFSFileSystem(squash_path) as wfs:
            with wfs.open("/f.txt", "wb") as f:
                f.write(b"data")
            raise RuntimeError("simulated error")

    assert not os.path.exists(squash_path)


# ---------------------------------------------------------------------------
# xarray / zarr round-trip
# ---------------------------------------------------------------------------


def test_xarray_zarr_write_read_roundtrip(tmp_path):
    """xarray dataset survives a write-to-squashfs / read-back round-trip."""
    squash_path = str(tmp_path / "xarray_roundtrip.squash")

    ds_orig = xr.Dataset(
        {"temperature": (("x", "y"), np.arange(12, dtype=float).reshape(3, 4))},
        coords={"x": [1, 2, 3], "y": [10, 20, 30, 40]},
    )

    # Write dataset via SquashFSFileSystem (write mode inferred)
    with SquashFSFileSystem(squash_path) as wfs:
        store = wfs.get_mapper("/")
        ds_orig.to_zarr(store, mode="w")

    # Read back via read-only SquashFSFileSystem
    rfs = SquashFSFileSystem(squash_path)
    ds_read = xr.open_dataset(
        "squashfs:///",
        engine="zarr",
        consolidated=False,
        backend_kwargs={"storage_options": {"fo": squash_path}},
    )
    xr.testing.assert_equal(ds_orig, ds_read)
    rfs.close()


def test_multiple_datasets_staged_correctly(tmp_path):
    """Multiple zarr datasets can be staged into one SquashFS image.

    Verifies that each dataset's zarr structure (metadata + data chunks)
    is present at the expected sub-path in the final SquashFS image.
    """
    squash_path = str(tmp_path / "multi.squash")

    ds1 = xr.Dataset({"a": ("x", np.arange(5, dtype=float))})
    ds2 = xr.Dataset({"b": ("y", np.arange(3, dtype=float))})

    with SquashFSFileSystem(squash_path) as wfs:
        ds1.to_zarr(wfs.get_mapper("/ds1.zarr"), mode="w", zarr_format=3)
        ds2.to_zarr(wfs.get_mapper("/ds2.zarr"), mode="w", zarr_format=3)

    # Verify structure via read-only filesystem
    rfs = SquashFSFileSystem(squash_path)
    root_entries = rfs.ls("/", detail=False)
    assert any("ds1.zarr" in e for e in root_entries)
    assert any("ds2.zarr" in e for e in root_entries)

    # zarr v3 uses zarr.json for both groups and arrays (no .zgroup / .zarray)
    assert rfs.exists("ds1.zarr/zarr.json")
    assert rfs.exists("ds1.zarr/a/zarr.json")
    assert rfs.exists("ds2.zarr/zarr.json")
    assert rfs.exists("ds2.zarr/b/zarr.json")
    rfs.close()


# ---------------------------------------------------------------------------
# URL-syntax write (one-liner, storage_options)
# ---------------------------------------------------------------------------


def test_url_syntax_write_read_roundtrip(tmp_path):
    """xarray can write via URL syntax and read back the result.

    Write:  ds.to_zarr("squashfs:///data.zarr", storage_options={"fo": path})
    Read:   xr.open_dataset("squashfs:///data.zarr", ...,
                            backend_kwargs={"storage_options": {"fo": path}})

    The SquashFS image is created automatically when the write-mode filesystem
    is garbage-collected; call ``gc.collect()`` after ``to_zarr`` to trigger
    the commit before reading back.
    """
    squash_path = str(tmp_path / "url_roundtrip.squash")

    ds_orig = xr.Dataset(
        {"temperature": (("x", "y"), np.arange(12, dtype=float).reshape(3, 4))},
        coords={"x": [1, 2, 3], "y": [10, 20, 30, 40]},
    )

    # Write using the URL one-liner — no explicit context manager needed.
    ds_orig.to_zarr(
        "squashfs:///data.zarr",
        consolidated=False,
        storage_options={"fo": squash_path},
    )
    # Break zarr's asyncio reference cycles so __del__ fires and mksquashfs runs.
    gc.collect()

    assert tmp_path.joinpath("url_roundtrip.squash").exists(), (
        "SquashFS image was not created by auto-commit"
    )

    # Read back using the URL syntax.
    ds_read = xr.open_dataset(
        "squashfs:///data.zarr",
        engine="zarr",
        consolidated=False,
        backend_kwargs={"storage_options": {"fo": squash_path}},
    )
    assert tmp_path.joinpath("url_roundtrip.squash").exists(), (
        "SquashFS image was not committed before read-back"
    )
    xr.testing.assert_equal(ds_orig, ds_read)
