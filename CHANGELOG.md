# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0]

### Added

- `cll` launcher: run Claude Code against a local LM Studio model.
- Normalizing reverse proxy that folds every non-leading `system` message into the
  single leading `system` block, fixing the "System message must be at the beginning"
  chat-template error for Qwen and other strict-template models. Runs on an ephemeral
  per-session port and streams responses through unbuffered.
- Model selection: `-m/--model` (exact id or unique substring), `--pick` menu,
  `$CLL_MODEL` default, current-loaded-model detection.
- `--list-models` and `--doctor` helpers.
- Standalone `claude-lms-proxy` console script.
- Packaging: PyPI metadata, a Homebrew formula, and GitHub Actions CI.

[Unreleased]: https://github.com/WillieCubed/claude-lms/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/WillieCubed/claude-lms/releases/tag/v0.1.0
