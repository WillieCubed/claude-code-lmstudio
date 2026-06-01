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

For how the pieces fit together (the launcher, the proxy, the request flow, and the
lifecycle), see [docs/reference/architecture.md](docs/reference/architecture.md).

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
cll [-m MODEL] [--pick] [--models] [--set-default MODEL] [--doctor] [claude args...]
```

- `cll` — launch Claude Code on a local model. **Any unrecognized arguments are forwarded
  to `claude`** — e.g. `cll --dangerously-skip-permissions -p "summarize this repo"`.
- `-m, --model MODEL` — model id, **exact or a unique substring** (`qwen3.6` →
  `qwen/qwen3.6-35b-a3b`). Ambiguous substrings list the candidates.
- `--pick` — choose a model from an annotated menu at launch.
- `--models` (or `cll models`) — print a table of available models (arch, quant, which is
  loaded/default) and exit.
- `--list-models` — print bare model ids and exit (handy for scripts and completion).
- `--set-default MODEL` / `--clear-default` — save (or clear) the default model.
- `--doctor` — check your environment (claude on PATH, LM Studio reachable, loaded model,
  defaults, available models) and exit.
- `--lmstudio-url URL` — point at a non-default LM Studio server.

`cll` starts LM Studio's server automatically (via the `lms` CLI, if installed), spins up
the normalizer on an ephemeral localhost port for the session, runs `claude`, and tears
everything down on exit.

### Passing flags to `claude`

`cll` consumes only its own flags (above); everything else is forwarded verbatim:

```bash
cll --dangerously-skip-permissions
cll -m gpt-oss-20b --permission-mode plan -p "explain this repo"
```

### Choosing a model

```bash
cll --models                        # see what's available
cll --set-default qwen/qwen3.6-27b  # pin a default (saved to config)
cll -m qwen3.6                      # one-off, by substring
cll --pick                          # annotated menu
```

Resolution order: **`-m/--model` → `--pick` → `$CLL_MODEL` → saved default
(`cll --set-default`) → currently-loaded model → the only model → menu.** The saved
default lives in `~/.config/claude-lms/config.json`; `CLL_MODEL` is a one-off override.

### Shell completion

Complete model ids with `cll -m <TAB>`:

```bash
# zsh — put the completion on your fpath:
mkdir -p ~/.zfunc && cp completions/_cll ~/.zfunc/_cll
# then in ~/.zshrc, before compinit:
#   fpath=(~/.zfunc $fpath); autoload -Uz compinit; compinit

# bash — source it from ~/.bashrc:
source /path/to/claude-lms/completions/cll.bash
```

### Configuration

| Variable / file                   | Purpose                                              |
| --------------------------------- | ---------------------------------------------------- |
| `cll --set-default` → config.json | Persistent default model                             |
| `CLL_MODEL`                       | One-off default-model override (beats the config)    |
| `LM_STUDIO_URL`                   | LM Studio base URL (default `http://localhost:1234`) |
| `CLL_AUTH_TOKEN`                  | Dummy auth token sent to the endpoint (`lm-studio`)  |

---

## Compatibility

Any model LM Studio can serve works. Models with strict chat templates (e.g.
**Qwen3.5 / Qwen3.6**) only work *with this proxy in front* — that's the whole point.
Tolerant-template models (e.g. `gpt-oss`, OLMo, Mistral) work either way. Tool calling
and streaming both pass through unchanged.

## Performance

The proxy is thin — it adds single-digit milliseconds (parse, fold stray system messages
only when present, forward) and streams responses with `TCP_NODELAY` and `read1`, so
tokens appear the instant LM Studio emits them. **The latency you feel is the local model
generating tokens, not the proxy.** To speed it up:

- **use a lighter model** for interactive work — `cll -m gpt-oss-20b`;
- **lower Claude Code's thinking effort** (reasoning models like Qwen think for a long
  time even on trivial prompts);
- **load the model with a smaller context** — `lms load <model> -c 65536` (a 256k context
  is much slower to prefill than you need for most turns);
- **enable Flash Attention / KV-cache quantization and full GPU offload** in LM Studio.

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
pytest                         # tests for the normalizer, CLI, and proxy
ruff check .
```

See [docs/reference/architecture.md](docs/reference/architecture.md) for how it works,
and [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

## License

This repo uses the [MIT License](LICENSE).
