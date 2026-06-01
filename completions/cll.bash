# bash completion for cll.
#
# Install: source this file from your ~/.bashrc, e.g.
#   source /path/to/claude-lms/completions/cll.bash
#
# Completes model ids (from `cll --list-models`) after -m/--model/--set-default,
# and cll's own flags otherwise.
_cll() {
  local cur prev
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"
  case "$prev" in
    -m | --model | --set-default)
      COMPREPLY=($(compgen -W "$(cll --list-models 2>/dev/null)" -- "$cur"))
      return
      ;;
  esac
  COMPREPLY=($(compgen -W "-m --model --pick --models --list-models --set-default --clear-default --doctor --lmstudio-url -V --version" -- "$cur"))
}
complete -F _cll cll
