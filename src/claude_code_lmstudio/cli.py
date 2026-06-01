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


def list_models(base_url: str) -> list[str]:
    """Return downloadable chat model ids from LM Studio (embeddings excluded)."""
    data = _get_json(base_url.rstrip("/") + "/v1/models")
    if not data:
        return []
    ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
    return [i for i in ids if "embed" not in i.lower()]


def loaded_model(base_url: str) -> str | None:
    """Best-effort: the id of the model currently loaded in LM Studio, if any.

    Uses LM Studio's native REST endpoint (``/api/v0/models``), which reports a
    per-model ``state``. Returns ``None`` if unavailable.
    """
    data = _get_json(base_url.rstrip("/") + "/api/v0/models")
    if not data:
        return None
    for model in data.get("data", []):
        mid = model.get("id", "")
        if model.get("state") == "loaded" and mid and "embed" not in mid.lower():
            return mid
    return None


def ensure_lmstudio(base_url: str) -> bool:
    """Ensure the LM Studio server is reachable, starting it via ``lms`` if needed."""
    if list_models(base_url):
        return True
    if shutil.which("lms"):
        subprocess.run(
            ["lms", "server", "start"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if list_models(base_url):
            return True
    return False


def pick_model(models: list[str]) -> str | None:
    """Prompt the user to choose a model from a numbered menu."""
    if not models:
        return None
    _eprint("Select a model:")
    for index, model in enumerate(models, 1):
        _eprint(f"  {index}) {model}")
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

    1. ``-m/--model``  2. ``--pick`` menu  3. ``$CLL_MODEL``
    4. the model currently loaded in LM Studio  5. the only model, if there is one
    6. otherwise an interactive menu.
    """
    if args.model:
        return args.model
    if args.pick:
        return pick_model(models)
    if os.environ.get("CLL_MODEL"):
        return os.environ["CLL_MODEL"]
    current = loaded_model(base_url)
    if current:
        return current
    if len(models) == 1:
        return models[0]
    return pick_model(models)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cll",
        description="Launch Claude Code against a local LM Studio model. "
        "Unrecognized arguments are forwarded to `claude`.",
    )
    parser.add_argument("-m", "--model", help="model id to use (e.g. qwen/qwen3.6-35b-a3b)")
    parser.add_argument(
        "--pick", action="store_true", help="choose a model from a menu at launch"
    )
    parser.add_argument(
        "--lmstudio-url",
        default=os.environ.get("LM_STUDIO_URL", DEFAULT_LMSTUDIO_URL),
        help="LM Studio base URL (default: %(default)s)",
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, claude_args = parser.parse_known_args(argv)
    base_url = args.lmstudio_url.rstrip("/")

    if shutil.which("claude") is None:
        _eprint(
            "cll: 'claude' (Claude Code) not found on PATH.\n"
            "     Install it from https://claude.com/claude-code"
        )
        return 127

    if not ensure_lmstudio(base_url):
        _eprint(
            f"cll: LM Studio is not reachable at {base_url}.\n"
            "     Start its local server (e.g. `lms server start`) and make sure a "
            "model is available."
        )
        return 1

    models = list_models(base_url)
    model = resolve_model(args, base_url, models)
    if not model:
        _eprint("cll: no model selected.")
        return 1
    if models and model not in models:
        _eprint(f"cll: model '{model}' is not available in LM Studio.")
        model = pick_model(models)
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
