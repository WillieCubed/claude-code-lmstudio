# Contributing

Thanks for your interest in improving claude-lms.

## Development setup

```bash
git clone https://github.com/WillieCubed/claude-lms
cd claude-lms
uv tool install --editable .   # or: pip install -e ".[dev]"
```

## Before opening a PR

```bash
ruff check .
pytest
```

- Keep the package **dependency-free** (standard library only). It's a big part of why
  this is easy to install and trust.
- The normalizer's behavior is pinned by `tests/test_normalize.py`. If you change how
  requests are rewritten, update those tests in the same change.
- Match the existing style: type hints, short docstrings, `ruff`-clean.

## Reporting bugs

Include the model id, the LM Studio version, and the exact error. `cll --doctor`
output is helpful. If it's a chat-template rejection, the upstream error text and the
offending model's template are the most useful details.

## Releasing (maintainers)

Releases are automated by `.github/workflows/release.yml`.

1. Update `CHANGELOG.md` and bump the version in `pyproject.toml` and
   `src/claude_lms/__init__.py`.
2. Tag `vX.Y.Z` and push the tag.

Pushing the tag builds the package, creates the GitHub release, and bumps the formula in
`WillieCubed/homebrew-tap`. The Homebrew step is gated on the `HOMEBREW_BUMP` repository
variable and the `HOMEBREW_TAP_TOKEN` secret. The tap holds the source of truth for the
formula. `claude-lms` is not published to a package index — distribution is Homebrew and
source installs.

For the full automated and manual release procedures (and the one-time setup), see
[docs/reference/releasing.md](docs/reference/releasing.md).
