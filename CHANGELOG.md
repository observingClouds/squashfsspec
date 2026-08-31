# CHANGELOG

## Unreleased

### Features

- Add write mode

### Fixes

- Guard `SquashFSFileSystem.__del__` against `AttributeError` when `__init__`
  fails before `_closed` is set.

### Documentation

- Update `README.md` with write usage examples using the unified `squashfs`
  protocol (no separate class or protocol needed).

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
