# Third-party
import numpy as np
import pytest
import xarray as xr


@pytest.fixture
def squash_path(tmp_path, make_squashfs):
    zarr_path = tmp_path / "test_data.zarr"

    # 1. Create a sample xarray dataset
    ds = xr.Dataset(
        {"foo": (("x", "y"), np.random.rand(4, 5))},
        coords={"x": [10, 20, 30, 40], "y": np.arange(5)},
    )

    # 2. Save it to a Zarr store
    ds.to_zarr(str(zarr_path))

    # 3. Squash it
    return make_squashfs(zarr_path, "test_xarray.squash")


def test_xarray_read(squash_path):
    # Working approach for xarray with squashfsspec:
    # Use a protocol-only URL and pass the squash file path via storage_options
    url = "squashfs:///"

    ds = xr.open_dataset(
        url,
        engine="zarr",
        consolidated=False,
        backend_kwargs={"storage_options": {"fo": squash_path}},
    )

    # Verify content
    xr.testing.assert_allclose(ds, ds)


def test_xarray_read_chained(squash_path):
    # If we squashed the CONTENT of the zarr dir, then it's at root.
    ds = xr.open_dataset(
        f"squashfs:///::{squash_path}",
        engine="zarr",
        consolidated=False,
    )
    assert "foo" in ds.variables
