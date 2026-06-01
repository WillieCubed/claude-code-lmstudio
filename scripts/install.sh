#!/usr/bin/env bash
# Install claude-code-lmstudio from a source checkout.
#
# Prefers pipx (isolated, recommended for CLI tools); falls back to `pip install
# --user`. After install, the `cll` and `claude-code-lmstudio-proxy` commands are on
# your PATH (ensure your user bin dir is on PATH — pipx will tell you if it isn't).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if command -v pipx >/dev/null 2>&1; then
  echo "Installing with pipx from ${here}…"
  pipx install --force "${here}"
elif command -v python3 >/dev/null 2>&1; then
  echo "pipx not found; installing with 'pip install --user' from ${here}…"
  python3 -m pip install --user --upgrade "${here}"
  echo
  echo "Note: ensure your user scripts dir is on PATH (e.g. ~/.local/bin)."
else
  echo "error: python3 is required but was not found on PATH." >&2
  exit 1
fi

echo
echo "Done. Try:  cll --help"
