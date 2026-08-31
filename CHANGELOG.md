# CHANGELOG

## Unreleased

### Features

- Add write mode to `SquashFSFileSystem`: mode is inferred automatically
  (write when the target path does not exist; read otherwise) or forced via
  `mode="w"`.
- Add `discard()` method to abandon a write session without creating any file.
- Context-manager `__exit__` discards staged data when an exception is raised,
  ensuring no partial SquashFS image is left behind.
- Support one-liner URL write syntax — xarray can now write directly to a new
  SquashFS image without an explicit context manager:

  ```python
  ds.to_zarr(
      "squashfs:///zarr1.zarr",
      consolidated=False,
      storage_options={"fo": "output.squash"},
  )
  ```

  After `to_zarr` returns, call `gc.collect()` to break zarr's asyncio
  reference cycles; the write-mode filesystem's `__del__` then runs
  `mksquashfs` automatically.

### Fixes

- Guard `SquashFSFileSystem.__del__` against `AttributeError` when `__init__`
  fails before `_closed` is set.
- Fix `__del__` in write mode to auto-commit (call `mksquashfs`) on GC
  instead of silently discarding staged data, enabling the URL one-liner
  write syntax (caller calls `gc.collect()` after `to_zarr`).

### Documentation

- Update `README.md` with both write usage patterns: URL one-liner and explicit
  context manager.

## v0.1.4 (2026-05-01)
- Fixing pypi release

## v0.1.3 (2026-05-01)

### Fixes
- Fix version number ([#22](https://github.com/observingClouds/squashfsspec/pull/22))

## v0.1.2 (2026-05-01)

### Changes
- Added closing of file system and sub-files ([#20](https://github.com/observingClouds/squashfsspec/pull/20))

## v0.1.1 (2026-04-29)

### Tests

- Add tests for README code examples, extracting code blocks directly from `README.md` to keep documentation and tests in sync ([#15](https://github.com/observingClouds/squashfsspec/pull/15))

### Documentation

- Fix protocol name in README: `fsspec.filesystem("squash", ...)` → `fsspec.filesystem("squashfs", ...)` ([#15](https://github.com/observingClouds/squashfsspec/pull/15))
- Fix `consolidated=False` → `consolidated=True` in the *Accessing Multiple Datasets* README example ([#15](https://github.com/observingClouds/squashfsspec/pull/15))
- Remove unused `from squashfsspec import SquashFSFileSystem` import from README usage example ([#16](https://github.com/observingClouds/squashfsspec/pull/16))

### Dependencies

- `[actions/checkout](https://github.com/actions/checkout)`: 4 → 6 ([#3](https://github.com/observingClouds/squashfsspec/pull/3))
- `[peter-evans/create-pull-request](https://github.com/peter-evans/create-pull-request)`: 7 → 8 ([#2](https://github.com/observingClouds/squashfsspec/pull/2))
- `[prefix-dev/setup-pixi](https://github.com/prefix-dev/setup-pixi)`: 0.8.1 → 0.9.5 ([#1](https://github.com/observingClouds/squashfsspec/pull/1))

## v0.1.0 Initial release (2026-04-28)

This is the initial release with the basic functionality implemented to read squashfs files with fsspec.
