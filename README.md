# claude-lms

[![CI](https://github.com/WillieCubed/claude-lms/actions/workflows/ci.yml/badge.svg)](https://github.com/WillieCubed/claude-lms/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)

Run [Claude Code](https://claude.com/claude-code) against your **local** models in
[LM Studio](https://lmstudio.ai) — including Qwen, GLM, and other models whose chat
templates otherwise reject Claude Code's requests with:

```
API Error: 500 ... Jinja Exception: System message must be at the beginning.
```

`cll` launches Claude Code wired to LM Studio's local Anthropic-compatible endpoint,
through a tiny normalizing proxy that fixes that error for any model.

```bash
cll                       # use the loaded / default local model
cll -m qwen3.6            # exact id or unique substring -> qwen/qwen3.6-35b-a3b
cll --pick               # choose from a menu at launch
cll --doctor             # check your setup
```

---

## Why this exists

LM Studio natively serves the Anthropic Messages API (`/v1/messages`), so in principle
you can point Claude Code at it with just environment variables. In practice, several
of the most capable local models fail immediately:

```
Jinja Exception: System message must be at the beginning.
```

### Root cause

Claude Code's request contains **two system messages in different positions**:

- the top-level `system` field (its main system prompt), rendered first; **and**
- a second **`system`-role message inside the `messages` array**, after the first user
  turn. This is typically hook-injected context (e.g. a `SessionStart` hook's output).

So the rendered conversation is `system → user → system`. Strict chat templates —
notably **Qwen3.5 / Qwen3.6** — contain a hard guard:

```jinja
{%- if message.role == "system" and not loop.first %}
    {{- raise_exception('System message must be at the beginning.') }}
```

The trailing system message isn't first, so template rendering aborts with HTTP 400
**before inference even starts**. It is *not* a RAM, tool-calling, or context-length
issue. Models with tolerant templates (`gpt-oss`, OLMo, Mistral) work fine; strict
ones (Qwen) don't. The same failure has been reported against other agents
([opencode](https://github.com/anomalyco/opencode/issues/16560),
[open-webui](https://github.com/open-webui/open-webui/issues/22505),
[llama.cpp](https://github.com/ggml-org/llama.cpp/issues/20733)).

### The fix

A small reverse proxy sits between Claude Code and LM Studio and **folds every
non-leading `system` message into the single leading `system` block** before
forwarding. The rendered conversation becomes `system → user`, which every template
accepts. Responses stream through unbuffered, so live token streaming still works.

This fixes the whole class of problem — any strict template, any hook-injected system
message — instead of patching one model's Jinja template by hand.

---

## Install

Requires the [`claude` CLI](https://claude.com/claude-code) and LM Studio with at least
one model downloaded.

### Homebrew (recommended)

```bash
brew install WillieCubed/tap/claude-lms
```

### Python (from source)

Requires Python 3.8+. Install from a checkout:

```bash
git clone https://github.com/WillieCubed/claude-lms
cd claude-lms
uv tool install .        # or: pipx install .   or: pip install .
```

Or straight from GitHub, without cloning:

```bash
uv tool install git+https://github.com/WillieCubed/claude-lms
```

`claude-lms` is not published to a package index — install via Homebrew or from source.

---

## Usage

```bash
cll [-m MODEL] [--pick] [--list-models] [--doctor] [--lmstudio-url URL] [claude args...]
```

- `cll` — launch Claude Code on a local model. Any unrecognized arguments are passed
  straight through to `claude` (e.g. `cll -p "summarize this repo"`).
- `-m, --model MODEL` — model id, **exact or a unique substring** (`qwen3.6` →
  `qwen/qwen3.6-35b-a3b`). Ambiguous substrings list the candidates.
- `--pick` — choose a model from a numbered menu at launch.
- `--list-models` — print available models and exit.
- `--doctor` — check your environment (claude on PATH, LM Studio reachable, loaded
  model, available models) and exit.
- `--lmstudio-url URL` — point at a non-default LM Studio server.

`cll` starts LM Studio's server automatically (via the `lms` CLI, if installed), spins
up the normalizer on an ephemeral localhost port for the session, runs `claude`, and
tears everything down on exit.

### Model selection order

1. `-m/--model` (exact id or unique substring)
2. `--pick` menu
3. `$CLL_MODEL`
4. the model currently loaded in LM Studio
5. the only downloaded model, if there is exactly one
6. otherwise, an interactive menu

Set a personal default in your shell profile:

```bash
export CLL_MODEL="qwen/qwen3.6-35b-a3b"
```

### Configuration

| Variable         | Default                  | Purpose                                  |
| ---------------- | ------------------------ | ---------------------------------------- |
| `CLL_MODEL`      | _(unset)_                | Default model when none is given         |
| `LM_STUDIO_URL`  | `http://localhost:1234`  | LM Studio server base URL                |
| `CLL_AUTH_TOKEN` | `lm-studio`              | Dummy auth token sent to the endpoint    |

---

## Compatibility

Any model LM Studio can serve works. Models with strict chat templates (e.g.
**Qwen3.5 / Qwen3.6**) only work *with this proxy in front* — that's the whole point.
Tolerant-template models (e.g. `gpt-oss`, OLMo, Mistral) work either way. Tool calling
and streaming both pass through unchanged.

## The proxy on its own

The normalizer can run standalone (e.g. for other Anthropic-compatible clients):

```bash
LM_STUDIO_URL=http://localhost:1234 LM_PROXY_PORT=1366 claude-lms-proxy
# then point your client at http://localhost:1366
```

## Uninstall

Matches however you installed it:

```bash
uv tool uninstall claude-lms    # uv
pipx uninstall claude-lms       # pipx
pip uninstall claude-lms        # pip
brew uninstall claude-lms       # Homebrew
```

## Development

```bash
uv tool install --editable .   # or: pip install -e ".[dev]"
pytest                         # unit tests for the normalizer + CLI helpers
ruff check .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

## License

This repo uses the [MIT License](LICENSE).
