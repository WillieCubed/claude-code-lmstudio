# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.3]

### Added

- Easier, more discoverable model selection:
  - `cll --set-default MODEL` / `--clear-default` — persist a default model to
    `~/.config/claude-lms/config.json` (no shell-profile editing). `CLL_MODEL` stays as a
    one-off override.
  - `cll --models` (and `cll models`) — a table of available models with arch, quant, and
    which is loaded/default.
  - `--pick` menu now annotates each model (arch · quant, loaded ★, default).
  - Shell tab-completion for `cll -m <TAB>` (zsh + bash) under `completions/`.
  - A launch hint pointing at `--pick` / `--set-default` when the model is auto-resolved.

### Changed

- Model resolution order now includes the saved default: `-m/--model` → `--pick` →
  `$CLL_MODEL` → saved default → loaded model → only model → menu.

## [0.1.2]

### Changed

- Performance: the proxy sets `TCP_NODELAY` so streamed tokens are not briefly buffered,
  skips the JSON re-encode of the request body when it carries no stray system message
  (nothing to fold), and `cll` no longer fetches the model list twice at startup. These
  are small wins — the dominant latency is the local model, not the proxy.

### Added

- `docs/reference/architecture.md`: a short explanation of the launcher, the proxy, the
  request flow, the lifecycle, and the performance levers. README gained Performance and
  architecture pointers.

## [0.1.1]

### Fixed

- The proxy no longer writes to the terminal. It runs in-process inside `cll`, sharing
  stderr with the Claude Code TUI; benign client disconnects previously dumped
  `ConnectionResetError` tracebacks to stderr and corrupted the display. Connection
  errors are now swallowed, and any diagnostics go to a log file behind `CLAUDE_LMS_DEBUG`.

### Changed

- Streaming uses `read1`, forwarding tokens as soon as LM Studio emits them (smoother
  output) and without copying each chunk into a combined buffer.
- Distribution is now Homebrew + source installs; PyPI publishing was dropped.

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

[Unreleased]: https://github.com/WillieCubed/claude-lms/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/WillieCubed/claude-lms/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/WillieCubed/claude-lms/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/WillieCubed/claude-lms/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/WillieCubed/claude-lms/releases/tag/v0.1.0
