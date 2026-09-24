# Sourced by the foundry hook scripts (not a hook itself). Reads the hook's
# stdin JSON into $input, moves to the session's working directory, and
# defines edited_files, which prints each edited path on its own line:
#   Claude Code — tool_input.file_path (absolute)
#   Codex       — the apply_patch patch in tool_input.command, with paths
#                 relative to cwd ("*** Add File:", "*** Update File:",
#                 "*** Move to:" lines; deleted files are skipped)
#   Antigravity — toolCall.args.TargetFile (absolute); no cwd in the
#                 payload, so the first workspace path stands in for it
# Hook scripts must print nothing on stdout: Codex treats any JSON there
# that isn't hook output as a failed hook run.
input=$(cat)
cd "$(printf '%s' "$input" | jq -r '.cwd // .workspacePaths[0] // "."')" 2>/dev/null || true

edited_files() {
  printf '%s' "$input" | jq -r '
    .tool_input.file_path // empty,
    .toolCall.args.TargetFile // empty,
    (.tool_input.command // empty | strings | split("\n")[]
      | select(test("^\\*\\*\\* (Add File|Update File|Move to): "))
      | sub("^\\*\\*\\* [A-Za-z ]+: "; ""))'
}
