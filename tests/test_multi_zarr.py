# Third-party
import numpy as np
import pytest
import xarray as xr


@pytest.fixture
def multi_zarr_squash(tmp_path, make_squashfs):
    base_dir = tmp_path / "data"
    base_dir.mkdir()
    # 1. Create multiple sample xarray datasets
    ds1 = xr.Dataset(
        {"foo": (("x", "y"), np.random.rand(4, 5))},
        coords={"x": [10, 20, 30, 40], "y": np.arange(5)},
    )
    ds2 = xr.Dataset(
        {"bar": (("a", "b"), np.random.rand(3, 3))},
        coords={"a": [1, 2, 3], "b": [1, 2, 3]},
    )

    # 2. Save them to Zarr stores in subdirectories
    ds1.to_zarr(str(base_dir / "ds1.zarr"), zarr_format=2)
    ds2.to_zarr(str(base_dir / "ds2.zarr"), zarr_format=2)

    # 3. Squash the entire directory
    return make_squashfs(base_dir, "test_multi.squash")


def test_multi_zarr_read(multi_zarr_squash):
    # Test reading ds1.zarr
    url1 = "squashfs:///ds1.zarr"
    ds1_read = xr.open_dataset(
        url1,
        engine="zarr",
        consolidated=True,
        backend_kwargs={"storage_options": {"fo": multi_zarr_squash}},
    )
    assert "foo" in ds1_read.variables

    # Test reading ds2.zarr
    url2 = "squashfs:///ds2.zarr"
    ds2_read = xr.open_dataset(
        url2,
        engine="zarr",
        consolidated=True,
        backend_kwargs={"storage_options": {"fo": multi_zarr_squash}},
    )
    assert "bar" in ds2_read.variables
