# SquashFSSpec

<p align="center">
  <img src="logo.jpeg" alt="SquashFSSpec Logo" width="300"/>
</p>

[![Tests](https://github.com/observingClouds/squashfsspec/actions/workflows/test.yaml/badge.svg)](https://github.com/haukeschulz/squashfsspec/actions/workflows/test.yaml)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI](https://img.shields.io/pypi/v/squashfsspec)](https://pypi.org/project/squashfsspec/)

A simple [fsspec](https://filesystem-spec.readthedocs.io/) driver for reading [SquashFS](https://en.wikipedia.org/wiki/SquashFS) files.

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
    backend_kwargs={"storage_options": {"fo": squashfs_path}},
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
