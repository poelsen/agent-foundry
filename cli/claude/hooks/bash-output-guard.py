#!/usr/bin/env python3
"""Claude Code PreToolUse hook (Bash): block `cat` of large files.

Dumping a whole file through the shell floods the context with output the
agent rarely needs in full. This denies a plain `cat <file>` (also inside
`&&`, `||` and `;` chains) when a file is over MAX_LINES lines or MAX_BYTES,
and tells the agent to read the part it needs with the Read tool, or to pipe
through head/tail/grep. Piped, redirected and heredoc uses of `cat` are left
alone. Deployed with bashOutputMaxChars in .claude/settings.json, which caps
the output of every command.
"""

import json
import re
import shlex
import sys
from pathlib import Path

MAX_LINES = 150
MAX_BYTES = 12_000


def large_files(command: str, cwd: Path) -> list[str]:
    found = []
    for segment in re.split(r"&&|\|\||;|\n", command):
        if re.search(r"[|<>]|\$\(|`", segment):
            continue
        try:
            words = shlex.split(segment)
        except ValueError:
            continue
        if not words or Path(words[0]).name != "cat":
            continue
        for word in words[1:]:
            path = cwd / Path(word).expanduser()
            if word.startswith("-") or not path.is_file():
                continue
            size = path.stat().st_size
            with path.open("rb") as fh:
                lines = sum(1 for _ in fh) if size < 50_000_000 else 10**9
            if lines > MAX_LINES or size > MAX_BYTES:
                found.append(f"{word} ({lines} lines)")
    return found


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return
    command = (event.get("tool_input") or {}).get("command") or ""
    found = large_files(command, Path(event.get("cwd") or Path.cwd()))
    if found:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Blocked: cat of large file(s) {', '.join(found)}. Use the Read tool with "
                "offset/limit for the part you need, or pipe through head/tail/grep."),
        }}))


if __name__ == "__main__":
    main()
