# CHANGELOG

## Unreleased

### Fixes

- Fix `requires-python` to `>=3.10` so the package installs on Python 3.14 ([#29](https://github.com/observingClouds/squashfsspec/pull/29))

### Dependencies

- Remove `zarr` from runtime dependencies and add a `test` extra with `pytest`, `numpy`, `xarray` and `zarr` ([#31](https://github.com/observingClouds/squashfsspec/pull/31))

### CI

- Run the test matrix on macOS (`macos-latest`) in addition to Linux; add `osx-arm64` to the pixi platforms ([#35](https://github.com/observingClouds/squashfsspec/pull/35))

### Changes

- Add MIT `LICENSE` file and declare the license in `pyproject.toml` ([#30](https://github.com/observingClouds/squashfsspec/pull/30))

### Tests

- Add shared `make_squashfs` fixture and behavioural tests for listing, traversal, reading, URL handling and offsets; known defects are marked `xfail(strict=True)` ([#33](https://github.com/observingClouds/squashfsspec/pull/33))
- Fail instead of skip when `mksquashfs` is missing and `SQUASHFSSPEC_REQUIRE_MKSQUASHFS` is set; CI sets it ([#34](https://github.com/observingClouds/squashfsspec/pull/34))

## v0.1.4 (2026-05-01)
- Fixing pypi release

### Documentation

- Add `HOW_TO_RELEASE.md` with step-by-step release instructions ([#25](https://github.com/observingClouds/squashfsspec/pull/25))

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
