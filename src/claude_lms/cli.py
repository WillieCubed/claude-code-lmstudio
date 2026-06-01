"""``cll`` -- launch Claude Code against a local model served by LM Studio.

Resolves a model, starts a per-session normalizing proxy on an ephemeral local port
(so concurrent sessions never collide and nothing is left running), then execs the
``claude`` CLI pointed at that proxy. All Claude-bound traffic stays on localhost.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from . import __version__
from .proxy import make_server

DEFAULT_LMSTUDIO_URL = "http://localhost:1234"


def _eprint(*args) -> None:
    print(*args, file=sys.stderr)


def _get_json(url: str, timeout: float = 5.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError):
        return None


# --- persistent config (the cll-managed default model) ----------------------------

def _config_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    return os.path.join(base, "claude-lms", "config.json")


def load_config() -> dict:
    try:
        with open(_config_path()) as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(config: dict) -> None:
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")


def configured_default() -> str | None:
    return load_config().get("default_model")


def effective_default() -> str | None:
    """The default model in force: the ``CLL_MODEL`` env override, else the config."""
    return os.environ.get("CLL_MODEL") or configured_default()


# --- LM Studio queries -------------------------------------------------------------

def list_models(base_url: str) -> list[str]:
    """Return downloadable chat model ids from LM Studio (embeddings excluded)."""
    data = _get_json(base_url.rstrip("/") + "/v1/models")
    if not data:
        return []
    ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
    return [i for i in ids if "embed" not in i.lower()]


def model_details(base_url: str) -> dict:
    """Map model id -> {arch, quant, state, ctx} from LM Studio's ``/api/v0/models``."""
    data = _get_json(base_url.rstrip("/") + "/api/v0/models") or {}
    details = {}
    for model in data.get("data", []):
        mid = model.get("id", "")
        if mid and "embed" not in mid.lower():
            details[mid] = {
                "arch": model.get("arch"),
                "quant": model.get("quantization"),
                "state": model.get("state"),
                "ctx": model.get("max_context_length"),
            }
    return details


def loaded_model(base_url: str) -> str | None:
    """Best-effort: the id of the model currently loaded in LM Studio, if any."""
    for mid, detail in model_details(base_url).items():
        if detail.get("state") == "loaded":
            return mid
    return None


def ensure_lmstudio(base_url: str) -> "list[str] | None":
    """Return available chat models, starting the LM Studio server if needed.

    Returns the model ids (embeddings excluded), or ``None`` if the server is
    unreachable or serves no chat models. Returning the list lets callers avoid a
    second ``/v1/models`` fetch.
    """
    models = list_models(base_url)
    if models:
        return models
    if shutil.which("lms"):
        subprocess.run(
            ["lms", "server", "start"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        models = list_models(base_url)
        if models:
            return models
    return None


# --- model selection ---------------------------------------------------------------

def match_model(requested: str, available: list[str]) -> tuple[str | None, list[str]]:
    """Resolve a possibly-partial model id against available ids.

    Returns ``(resolved, candidates)``: an exact id or unique substring match yields
    ``(id, [])``; an ambiguous substring yields ``(None, matches)``; no match yields
    ``(None, [])``.
    """
    if requested in available:
        return requested, []
    matches = [m for m in available if requested.lower() in m.lower()]
    if len(matches) == 1:
        return matches[0], []
    return None, matches


def _annotate(model: str, details: dict, default: str | None) -> str:
    detail = details.get(model, {})
    bits = [b for b in (detail.get("arch"), detail.get("quant")) if b]
    meta = f"  [{' · '.join(bits)}]" if bits else ""
    marks = []
    if detail.get("state") == "loaded":
        marks.append("loaded")
    if model == default:
        marks.append("default")
    mark = f"  ({', '.join(marks)})" if marks else ""
    return f"{model}{meta}{mark}"


def pick_model(
    models: list[str], details: dict | None = None, default: str | None = None
) -> str | None:
    """Prompt the user to choose a model from a numbered, annotated menu."""
    if not models:
        return None
    details = details or {}
    _eprint("Select a model:")
    for index, model in enumerate(models, 1):
        _eprint(f"  {index}) {_annotate(model, details, default)}")
    while True:
        try:
            choice = input("# ").strip()
        except EOFError:
            return None
        if not choice:
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(models):
            return models[int(choice) - 1]
        _eprint("Invalid selection.")


def resolve_model(args, base_url: str, models: list[str]) -> str | None:
    """Pick the model to use, in priority order.

    1. ``-m/--model`` (exact id or unique substring)  2. ``--pick`` menu
    3. ``$CLL_MODEL`` (one-off env override)  4. the persisted default
    (``cll --set-default``)  5. the model currently loaded in LM Studio
    6. the only model, if there is exactly one  7. otherwise an interactive menu.
    """
    def menu() -> str | None:
        return pick_model(models, model_details(base_url), effective_default())

    if args.model:
        resolved, candidates = match_model(args.model, models)
        if resolved:
            return resolved
        if candidates:
            _eprint(f"cll: '{args.model}' matches multiple models:")
            for candidate in candidates:
                _eprint(f"  - {candidate}")
            return None
        if models:
            _eprint(f"cll: model '{args.model}' not found in LM Studio.")
            return menu()
        return args.model
    if args.pick:
        return menu()
    if os.environ.get("CLL_MODEL"):
        return os.environ["CLL_MODEL"]
    if configured_default():
        return configured_default()
    current = loaded_model(base_url)
    if current:
        return current
    if len(models) == 1:
        return models[0]
    return menu()


# --- informational subcommands -----------------------------------------------------

def print_models_table(base_url: str) -> int:
    """Print a human-readable table of available models and exit."""
    models = ensure_lmstudio(base_url)
    if models is None:
        _eprint(f"cll: LM Studio is not reachable at {base_url}.")
        return 1
    details = model_details(base_url)
    default = effective_default()
    print(f"{'MODEL':36} {'ARCH':12} {'QUANT':9} STATE")
    for model in models:
        detail = details.get(model, {})
        flags = []
        if detail.get("state") == "loaded":
            flags.append("loaded")
        if model == default:
            flags.append("default")
        print(
            f"{model:36} {(detail.get('arch') or '?'):12} "
            f"{(detail.get('quant') or '?'):9} {' '.join(flags)}".rstrip()
        )
    return 0


def run_doctor(base_url: str) -> int:
    """Print an environment checklist and return 0 if everything looks ready."""
    claude = shutil.which("claude")
    lms = shutil.which("lms")
    models = list_models(base_url)
    reachable = bool(models)
    loaded = loaded_model(base_url)
    env_default = os.environ.get("CLL_MODEL")
    cfg_default = configured_default()

    checks = [
        (bool(claude), f"claude CLI            {claude or 'not found — https://claude.com/claude-code'}"),
        (True, f"lms CLI               {lms or 'not found (optional; auto-starts the server)'}"),
        (reachable, f"LM Studio server      {'reachable at ' + base_url if reachable else 'NOT reachable at ' + base_url}"),
    ]
    if loaded:
        checks.append((True, f"loaded model          {loaded}"))
    if env_default:
        checks.append((True, f"CLL_MODEL (env)       {env_default}"))
    if cfg_default:
        checks.append((True, f"default (config)      {cfg_default}"))

    for passed, message in checks:
        _eprint(f"  {'✓' if passed else '✗'} {message}")
    if models:
        _eprint(f"  · available models    {len(models)}")
        for model in models:
            _eprint(f"      {model}")

    ready = all(passed for passed, _ in checks)
    _eprint("")
    _eprint("cll: ready." if ready else "cll: not ready — resolve the ✗ items above.")
    return 0 if ready else 1


EPILOG = """\
examples:
  cll                              launch on the default model
  cll -m qwen3.6                   substring match -> qwen/qwen3.6-35b-a3b
  cll --pick                       choose a model from a menu
  cll models                       show a table of available models
  cll --set-default qwen3.6-27b    pin a default model
  cll --dangerously-skip-permissions   any unknown flag is forwarded to claude
  cll -p "explain this repo"       forward arguments to claude

model is chosen in this order:
  -m/--model · --pick · $CLL_MODEL · cll --set-default · loaded model · only model · menu

environment:
  CLL_MODEL        one-off default-model override (beats the saved default)
  LM_STUDIO_URL    LM Studio base URL (default http://localhost:1234)
  CLL_AUTH_TOKEN   dummy auth token sent to the endpoint (default lm-studio)
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cll",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Launch Claude Code against a local LM Studio model. "
        "Unrecognized arguments are forwarded to `claude`.",
        epilog=EPILOG,
    )
    parser.add_argument(
        "-m", "--model", help="model id, exact or unique substring (e.g. qwen3.6)"
    )
    parser.add_argument(
        "--pick", action="store_true", help="choose a model from a menu at launch"
    )
    parser.add_argument(
        "--models", action="store_true", help="show a detailed model table and exit"
    )
    parser.add_argument(
        "--list-models", action="store_true", help="list available model ids and exit"
    )
    parser.add_argument(
        "--set-default", metavar="MODEL", help="persist MODEL as the default, then exit"
    )
    parser.add_argument(
        "--clear-default", action="store_true", help="clear the saved default, then exit"
    )
    parser.add_argument(
        "--doctor", action="store_true", help="check your environment and exit"
    )
    parser.add_argument(
        "--lmstudio-url",
        default=os.environ.get("LM_STUDIO_URL", DEFAULT_LMSTUDIO_URL),
        help="LM Studio base URL (default: %(default)s)",
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, claude_args = parser.parse_known_args(argv)
    base_url = args.lmstudio_url.rstrip("/")

    # --- exits that don't launch claude ---
    if args.set_default:
        save_config({**load_config(), "default_model": args.set_default})
        _eprint(f"cll: default model set to '{args.set_default}'  ({_config_path()})")
        return 0
    if args.clear_default:
        config = load_config()
        config.pop("default_model", None)
        save_config(config)
        _eprint("cll: saved default cleared")
        return 0
    if args.doctor:
        return run_doctor(base_url)
    if args.models or claude_args == ["models"]:
        return print_models_table(base_url)
    if args.list_models:
        models = ensure_lmstudio(base_url)
        if models is None:
            _eprint(f"cll: LM Studio is not reachable at {base_url}.")
            return 1
        for model in models:
            print(model)
        return 0

    # --- launch claude ---
    if shutil.which("claude") is None:
        _eprint(
            "cll: 'claude' (Claude Code) not found on PATH.\n"
            "     Install it from https://claude.com/claude-code"
        )
        return 127

    models = ensure_lmstudio(base_url)
    if models is None:
        _eprint(
            f"cll: LM Studio is not reachable at {base_url}.\n"
            "     Start its local server (e.g. `lms server start`) and make sure a "
            "model is available."
        )
        return 1

    auto_resolved = not args.model and not args.pick
    model = resolve_model(args, base_url, models)
    if not model:
        _eprint("cll: no model selected.")
        return 1
    if models and model not in models:
        _eprint(f"cll: model '{model}' is not available in LM Studio.")
        model = pick_model(models, model_details(base_url), effective_default())
        if not model:
            return 1

    upstream = urlsplit(base_url)
    server = make_server(
        "127.0.0.1", 0, upstream.hostname or "localhost", upstream.port or 1234
    )
    host, port = server.server_address
    proxy_url = f"http://{host}:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = dict(os.environ)
    env["ANTHROPIC_BASE_URL"] = proxy_url
    env["ANTHROPIC_AUTH_TOKEN"] = os.environ.get("CLL_AUTH_TOKEN", "lm-studio")
    for var in (
        "ANTHROPIC_MODEL",
        "ANTHROPIC_SMALL_FAST_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL",
    ):
        env[var] = model
    # Don't let a stored cloud key shadow the local endpoint.
    env.pop("ANTHROPIC_API_KEY", None)

    _eprint(f"cll: Claude Code -> {model}  via LM Studio {base_url}  (normalizer {proxy_url})")
    if auto_resolved and len(models) > 1:
        _eprint("cll: (cll --pick to choose another · cll --set-default to pin one)")

    # Let the child own terminal signals (Ctrl-C); keep the proxy alive until it exits.
    previous = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        completed = subprocess.run(["claude", *claude_args], env=env)
        return completed.returncode
    finally:
        signal.signal(signal.SIGINT, previous)
        server.shutdown()


if __name__ == "__main__":
    sys.exit(main())
