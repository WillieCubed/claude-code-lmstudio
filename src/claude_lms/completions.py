"""Shell completion scripts and a turnkey installer.

``cll --install-completion`` writes the right script and wires it into the user's shell
rc file — no manual copy-paste. Idempotent: re-running won't duplicate the rc block.
"""
from __future__ import annotations

import os

ZSH = r"""#compdef cll
# zsh completion for cll (installed by `cll install-completion`).
_cll() {
  local prev="${words[CURRENT-1]}"
  if [[ "$prev" == (-m|--model|set-default) ]]; then
    local -a models
    models=(${(f)"$(cll list-models 2>/dev/null)"})
    compadd -- $models
    return
  fi
  compadd -- models list-models doctor set-default clear-default install-completion \
    -m --model --pick --lmstudio-url -V --version
}
_cll "$@"
"""

BASH = r"""# bash completion for cll (installed by `cll install-completion`).
_cll() {
  local cur prev
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"
  case "$prev" in
    -m | --model | set-default)
      COMPREPLY=($(compgen -W "$(cll list-models 2>/dev/null)" -- "$cur"))
      return
      ;;
  esac
  COMPREPLY=($(compgen -W "models list-models doctor set-default clear-default install-completion -m --model --pick --lmstudio-url -V --version" -- "$cur"))
}
complete -F _cll cll
"""

_MARKER_BEGIN = "# >>> claude-lms completion >>>"
_MARKER_END = "# <<< claude-lms completion <<<"


def detect_shell() -> str | None:
    """Return 'zsh' or 'bash' from $SHELL, or None if neither is detected."""
    name = os.path.basename(os.environ.get("SHELL", ""))
    if "zsh" in name:
        return "zsh"
    if "bash" in name:
        return "bash"
    return None


def _ensure_rc_block(rc_path: str, block: str) -> bool:
    """Append ``block`` (wrapped in markers) to ``rc_path`` unless already present.

    Returns True if the file was modified.
    """
    try:
        with open(rc_path) as handle:
            existing = handle.read()
    except OSError:
        existing = ""
    if _MARKER_BEGIN in existing:
        return False
    os.makedirs(os.path.dirname(rc_path), exist_ok=True)
    with open(rc_path, "a") as handle:
        handle.write(f"\n{_MARKER_BEGIN}\n{block.rstrip()}\n{_MARKER_END}\n")
    return True


def install(shell: str, home: str | None = None) -> list[str]:
    """Install completion for ``shell`` ('zsh' or 'bash'). Idempotent.

    Returns log lines describing what happened.
    """
    home = home or os.path.expanduser("~")
    messages: list[str] = []

    if shell == "zsh":
        comp_dir = os.path.join(home, ".zsh", "completions")
        os.makedirs(comp_dir, exist_ok=True)
        comp_file = os.path.join(comp_dir, "_cll")
        with open(comp_file, "w") as handle:
            handle.write(ZSH)
        messages.append(f"wrote {comp_file}")
        rc = os.path.join(home, ".zshrc")
        block = f'fpath=("{comp_dir}" $fpath)\nautoload -Uz compinit\ncompinit'
    elif shell == "bash":
        comp_dir = os.path.join(home, ".local", "share", "claude-lms")
        os.makedirs(comp_dir, exist_ok=True)
        comp_file = os.path.join(comp_dir, "cll.bash")
        with open(comp_file, "w") as handle:
            handle.write(BASH)
        messages.append(f"wrote {comp_file}")
        rc = os.path.join(home, ".bashrc")
        block = f'[ -f "{comp_file}" ] && source "{comp_file}"'
    else:
        raise ValueError(f"unsupported shell: {shell!r}")

    messages.append(f"updated {rc}" if _ensure_rc_block(rc, block) else f"{rc} already configured")
    return messages


def _strip_rc_block(rc_path: str) -> bool:
    """Remove the marker-wrapped block (and one preceding blank line) from ``rc_path``.

    Returns True if the file was modified.
    """
    try:
        with open(rc_path) as handle:
            content = handle.read()
    except OSError:
        return False
    if _MARKER_BEGIN not in content:
        return False
    kept, skipping = [], False
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == _MARKER_BEGIN:
            skipping = True
            if kept and kept[-1].strip() == "":
                kept.pop()  # drop the blank line install added before the block
            continue
        if stripped == _MARKER_END:
            skipping = False
            continue
        if not skipping:
            kept.append(line)
    with open(rc_path, "w") as handle:
        handle.write("".join(kept))
    return True


def uninstall(shell: str, home: str | None = None) -> list[str]:
    """Remove completion for ``shell`` (the script + the rc block). Idempotent.

    Returns log lines describing what happened.
    """
    home = home or os.path.expanduser("~")
    if shell == "zsh":
        comp_file = os.path.join(home, ".zsh", "completions", "_cll")
        rc = os.path.join(home, ".zshrc")
    elif shell == "bash":
        comp_file = os.path.join(home, ".local", "share", "claude-lms", "cll.bash")
        rc = os.path.join(home, ".bashrc")
    else:
        raise ValueError(f"unsupported shell: {shell!r}")

    messages: list[str] = []
    if os.path.exists(comp_file):
        os.remove(comp_file)
        messages.append(f"removed {comp_file}")
    else:
        messages.append(f"{comp_file} not present")
    messages.append(f"cleaned {rc}" if _strip_rc_block(rc) else f"{rc} had no completion block")
    return messages
