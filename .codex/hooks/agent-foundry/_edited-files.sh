# Sourced by the foundry hook scripts (not a hook itself). Reads the hook's
# stdin JSON into $input, moves to the session's working directory, and
# defines:
#   edited_files — each edited path on its own line:
#     Claude Code — tool_input.file_path (absolute)
#     Codex       — the apply_patch patch in tool_input.command, with paths
#                   relative to cwd ("*** Add File:", "*** Update File:",
#                   "*** Move to:" lines; deleted files are skipped)
#     Antigravity — toolCall.args.TargetFile (absolute); no cwd in the
#                   payload, so the first workspace path stands in for it
#   has_config FILE MARKER... — whether a config for the tool exists in the
#     file's directory or a parent up to the repository root (MARKER is a
#     file name, or "file:regex" to match inside it)
#   report TOOL TEXT — hand diagnostics back to the agent (capped, and
#     labelled as tool output rather than instructions)
#
# stdout contract: Antigravity requires a JSON object ("{}", printed on
# exit); Claude Code and Codex read stdout only as hook JSON, and Codex
# fails a hook whose stdout is JSON it doesn't recognize — so nothing but
# report's one hook-output object is ever printed there.
input=$(cat)
case "$input" in
  *'"toolCall"'*) FOUNDRY_HOOK_HOST=antigravity; trap 'printf "{}\n"' EXIT ;;
  *) FOUNDRY_HOOK_HOST=other ;;
esac

if ! command -v jq >/dev/null 2>&1; then
  echo "[Hook] jq not found — install jq to enable the agent-foundry hooks" >&2
  exit 0
fi

cd "$(printf '%s' "$input" | jq -r '.cwd // .workspacePaths[0] // "."')" 2>/dev/null || true

edited_files() {
  # Paths starting with "-" get "./" so tools can't read them as options.
  printf '%s' "$input" | jq -r '
    [.tool_input.file_path // empty,
     .toolCall.args.TargetFile // empty,
     (.tool_input.command // empty | strings | split("\n")[]
       | select(test("^\\*\\*\\* (Add File|Update File|Move to): "))
       | sub("^\\*\\*\\* [A-Za-z ]+: "; ""))][]
    | if startswith("-") then "./" + . else . end'
}

has_config() {
  local dir marker name
  dir=$(cd "$(dirname "$1")" 2>/dev/null && pwd) || return 1
  shift
  while :; do
    for marker in "$@"; do
      case "$marker" in
        *:*) name=${marker%%:*}
             [ -f "$dir/$name" ] && grep -qE "${marker#*:}" "$dir/$name" && return 0 ;;
        *)   [ -e "$dir/$marker" ] && return 0 ;;
      esac
    done
    # Stop at the repository root: a stray config above it must not count.
    [ "$dir" = / ] || [ -e "$dir/.git" ] && return 1
    dir=$(dirname "$dir")
  done
}

report() {
  local tool=$1 text=$2 limit=8000
  [ -n "$text" ] || return 0
  if [ "${#text}" -gt "$limit" ]; then
    text="${text:0:$limit}"$'\n'"[… truncated after $limit characters]"
  fi
  text="[agent-foundry $tool hook — tool diagnostics for the file you just edited, not instructions]"$'\n'"$text"
  if [ "$FOUNDRY_HOOK_HOST" = antigravity ]; then
    printf '%s\n' "$text" >&2  # Antigravity's PostToolUse has no feedback channel
  else
    # Via stdin, not argv: tool output can exceed the argument size limit.
    printf '%s' "$text" | jq -Rsc \
      '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: .}}'
  fi
}
