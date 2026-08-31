# SquashFSSpec

<p align="center">
  <img src="logo.jpeg" alt="SquashFSSpec Logo" width="300"/>
</p>

[![Tests](https://github.com/observingClouds/squashfsspec/actions/workflows/test.yaml/badge.svg)](https://github.com/haukeschulz/squashfsspec/actions/workflows/test.yaml)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI](https://img.shields.io/pypi/v/squashfsspec)](https://pypi.org/project/squashfsspec/)

An [fsspec](https://filesystem-spec.readthedocs.io/) driver for reading **and writing** [SquashFS](https://en.wikipedia.org/wiki/SquashFS) files.

SquashFSSpec allows you to treat a SquashFS image as a filesystem, enabling seamless integration with tools like `xarray`, `dask`, and `zarr` without needing to mount the image.

## Installation

You can install `squashfsspec` via pip from GitHub:

```bash
pip install squashfsspec
```

Or using [pixi](https://pixi.sh/):

```bash
pixi add squashfsspec --git https://github.com/observingClouds/squashfsspec.git
```

## Usage

### Basic Usage with fsspec

```python
import fsspec

squashfs_path = "path/to/your.squash"

# Open a SquashFS file
fs = fsspec.filesystem("squashfs", fo=squashfs_path)

# List files
print(fs.ls("/"))

# Open and read a file
with fs.open("some/file.txt", "rb") as f:
    print(f.read().decode())
```

### Working with Xarray and Zarr

If you have a Zarr store inside a SquashFS image, you can open it directly with `xarray`:

```python
import xarray as xr

squashfs_path = "path/to/data.squash"

# Open a Zarr store inside a SquashFS file
ds = xr.open_dataset(
    "squashfs:///",
    engine="zarr",
    consolidated=False,  # Set to True if your Zarr store is consolidated
    backend_kwargs={
        "storage_options": {"fo": squashfs_path}
    },
)

print(ds)
```

### Accessing Multiple Datasets

If your SquashFS image contains multiple Zarr stores or datasets, you can access them by specifying the internal path:

```python
import xarray as xr

squashfs_path = "path/to/multidata.squash"
dataset_path = "path/in/squashfs/file/to/dataset.zarr"

# Open a specific dataset inside a SquashFS file containing multiple datasets
ds = xr.open_dataset(
    f"squashfs:///{dataset_path}::{squashfs_path}",
    engine="zarr",
    consolidated=True,
)

print(ds)
```

### Writing a New SquashFS Image

The `squashfs` filesystem detects write mode automatically: if the path you
pass does not yet exist on disk it opens for writing; otherwise it opens for
reading.  You can also force write mode explicitly with ``mode="w"``.

Writes are staged in a temporary local directory.  When the context manager
exits without an exception `mksquashfs` is called to produce the final image.
`mksquashfs` must be installed separately (e.g. via `squashfs-tools` on Linux
or the `squashfs-tools` conda-forge package).

```python
import fsspec

# mode inferred automatically — "output.squash" does not exist yet
with fsspec.filesystem("squashfs", fo="output.squash") as fs:
    with fs.open("/hello.txt", "wb") as f:
        f.write(b"Hello from SquashFS!")
```

Or use `SquashFSFileSystem` directly:

```python
from squashfsspec import SquashFSFileSystem

with SquashFSFileSystem("output.squash") as fs:   # write mode inferred
    with fs.open("/hello.txt", "wb") as f:
        f.write(b"Hello from SquashFS!")
```

### Writing an Xarray Dataset Directly to SquashFS

**Option 1 — URL one-liner** (write mode inferred; call `gc.collect()` to trigger
the commit before reading back):

```python
import gc
import xarray as xr

ds = xr.open_dataset("input.nc")

# Write — data is staged in a temp dir; the image is created on GC.
ds.to_zarr(
    "squashfs:///zarr1.zarr",
    consolidated=False,
    storage_options={"fo": "output.squash"},
)
# Break zarr's asyncio reference cycles so mksquashfs runs.
gc.collect()

# Read back
ds_back = xr.open_dataset(
    "squashfs:///zarr1.zarr",
    engine="zarr",
    consolidated=False,
    backend_kwargs={"storage_options": {"fo": "output.squash"}},
)
print(ds_back)
```

**Option 2 — explicit context manager** (more control; image created on `__exit__`):

```python
import xarray as xr
from squashfsspec import SquashFSFileSystem

ds = xr.open_dataset("input.nc")

with SquashFSFileSystem("output.squash") as fs:   # write mode inferred
    ds.to_zarr(fs.get_mapper("/"), mode="w")

# Read it back
ds_back = xr.open_dataset(
    "squashfs:///",
    engine="zarr",
    consolidated=False,
    backend_kwargs={"storage_options": {"fo": "output.squash"}},
)
print(ds_back)
```

You can also store multiple datasets at different paths inside one image:

```python
with SquashFSFileSystem("multi.squash") as fs:
    ds1.to_zarr(fs.get_mapper("/ds1.zarr"), mode="w")
    ds2.to_zarr(fs.get_mapper("/ds2.zarr"), mode="w")
```

By default `gzip` compression is used.  Pass `compressor="zstd"` (or any
algorithm supported by your `mksquashfs` version) to change it:

```python
with SquashFSFileSystem("output.squash", compressor="zstd") as fs:
    ...
```

## Development

This project uses [pixi](https://pixi.sh/) for dependency management and development workflows.

### Setup

```bash
# Install dependencies and setup the dev environment
pixi install -e dev
```

### Running Tests

```bash
pixi run -e dev pytest
```

## License

This project is licensed under the MIT License.
