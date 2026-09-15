# How to Release a New Version

This document describes the steps to release a new version of `squashfsspec` to [PyPI](https://pypi.org/project/squashfsspec/).

## Prerequisites

- Write access to the [squashfsspec GitHub repository](https://github.com/observingClouds/squashfsspec)
- Familiarity with [Semantic Versioning](https://semver.org/)

## Release Steps

### 1. Update the Changelog

In `CHANGELOG.md`, rename the `## Unreleased` section to the new version and date, and add a fresh, empty `## Unreleased` section above it. Follow the existing format:

```markdown
## Unreleased

## vX.Y.Z (YYYY-MM-DD)

### Fixes
- ...

### Changes
- ...
```

`CHANGELOG.md` must always contain an `## Unreleased` section: every pull request adds its entry there, and the [Dependabot changelog workflow](.github/workflows/dependabot-auto-changelog.yml) aborts without it. A pre-commit hook fails if the section is missing.

### 2. Bump the Version Number

Update the `version` field in `pyproject.toml`:

```toml
[project]
version = "X.Y.Z"
```

### 3. Open a Pull Request

Commit the changelog and version bump changes, then open a pull request targeting `main`. Once the PR is reviewed and approved, merge it.

### 4. Create and Publish a GitHub Release

1. Go to the [Releases page](https://github.com/observingClouds/squashfsspec/releases) and click **Draft a new release**.
2. Click **Choose a tag**, type the new version tag (e.g. `vX.Y.Z`), and select **Create new tag on publish**.
3. Set the **Target** to `main`.
4. Use the version tag as the **Release title** (e.g. `vX.Y.Z`).
5. Copy the relevant section from `CHANGELOG.md` into the release description.
6. Click **Publish release**.

Publishing the release automatically triggers the [Release workflow](.github/workflows/release.yml), which builds and uploads the package to PyPI.

### 5. Verify the PyPI Release

After the workflow completes, confirm the new version is available on PyPI:

```
https://pypi.org/project/squashfsspec/
```
