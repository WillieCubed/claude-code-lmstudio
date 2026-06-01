# Releasing claude-lms

There are two paths: the **automated** workflow (default) and a **manual** fallback for
when you'd rather not use CI (or CI is unavailable). Both produce the same result: a
tagged GitHub release, a PyPI release, and an updated Homebrew formula in
[`WillieCubed/homebrew-tap`](https://github.com/WillieCubed/homebrew-tap).

The tap holds the source of truth for the Homebrew formula; this repo no longer carries a
copy.

---

## Automated (recommended)

Pushing a `vX.Y.Z` tag runs [`.github/workflows/release.yml`](../../.github/workflows/release.yml),
which builds the package, creates the GitHub release, publishes to PyPI (via Trusted
Publishing), and bumps the tap formula.

1. Bump the version in `pyproject.toml` **and** `src/claude_lms/__init__.py`, and update
   `CHANGELOG.md`.
2. Commit, then tag and push:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

The PyPI and Homebrew jobs are **gated** — they only run once configured (below), so a
tag pushed before setup just builds and creates the GitHub release.

### One-time setup for the automation

**PyPI (Trusted Publishing, no token stored):**

1. On PyPI, add a *pending publisher* (works before the project exists): Account →
   Publishing → add a GitHub publisher with
   - Owner: `WillieCubed`, Repository: `claude-lms`
   - Workflow: `release.yml`, Environment: `pypi`
2. Enable the gated job:

   ```bash
   gh variable set PYPI_PUBLISH --body true -R WillieCubed/claude-lms
   ```

**Homebrew auto-bump:**

1. Create a token with push access to `WillieCubed/homebrew-tap` (a fine-grained PAT
   scoped to that repo, Contents: read/write), then:

   ```bash
   gh secret set HOMEBREW_TAP_TOKEN -R WillieCubed/claude-lms      # paste the token
   gh variable set HOMEBREW_BUMP --body true -R WillieCubed/claude-lms
   ```

2. The formula must already exist in the tap — see *Bootstrap the formula* below for the
   first release. After that, the workflow keeps it current.

To publish the current version without cutting a new tag (e.g. the first PyPI release
once the publisher is configured), run the workflow manually:

```bash
gh workflow run release.yml -R WillieCubed/claude-lms
```

---

## Manual (fallback)

### 1. Build

```bash
python -m pip install build && python -m build   # or: uv build
# -> dist/claude_lms-X.Y.Z.tar.gz and dist/claude_lms-X.Y.Z-py3-none-any.whl
```

### 2. Publish to PyPI

Create an API token at <https://pypi.org/manage/account/token/>, then:

```bash
uv publish --token pypi-XXXXXXXX          # or: python -m twine upload dist/*
```

### 3. Create the GitHub release

```bash
gh release create vX.Y.Z dist/* --generate-notes -R WillieCubed/claude-lms
```

### 4. Update the Homebrew formula

```bash
# Checksum of the tag's source tarball:
curl -sL https://github.com/WillieCubed/claude-lms/archive/refs/tags/vX.Y.Z.tar.gz \
  | shasum -a 256
```

In `WillieCubed/homebrew-tap`, edit `Formula/claude-lms.rb` so `url` points at that tag
tarball and `sha256` is the value above, then commit and push. Verify:

```bash
brew update
brew install --build-from-source WillieCubed/tap/claude-lms
brew test WillieCubed/tap/claude-lms
brew audit --strict --online WillieCubed/tap/claude-lms
```

---

## Bootstrap the formula (first release only)

The auto-bump action updates an existing formula, so the first one is created by hand.
Add `Formula/claude-lms.rb` to the tap with the `url`/`sha256` for `v0.1.0`:

```ruby
class ClaudeLms < Formula
  include Language::Python::Virtualenv

  desc "Run Claude Code against local models in LM Studio"
  homepage "https://github.com/WillieCubed/claude-lms"
  url "https://github.com/WillieCubed/claude-lms/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "FILL_IN"   # shasum -a 256 of the tarball above
  license "MIT"
  head "https://github.com/WillieCubed/claude-lms.git", branch: "main"

  depends_on "python@3.13"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "usage: cll", shell_output("#{bin}/cll --help")
  end
end
```
