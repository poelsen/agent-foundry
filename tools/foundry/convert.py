"""Parse foundry sources, which are authored in Claude Code's formats, for
conversion into other CLIs' formats (see the adapters and shared.py)."""

from __future__ import annotations

import json
from pathlib import Path

# Claude tools that modify files. An agent granted none of them is
# read-only, which Codex and Antigravity can enforce.
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Scalar ``key: value`` frontmatter (all foundry agents use) and body."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            meta[key.strip()] = value.strip().strip("\"'")
    return meta, text[end + 4:].lstrip("\n")


def agent_tools(meta: dict[str, str]) -> set[str]:
    """The Claude tool names an agent's frontmatter grants."""
    return {t.strip() for t in meta.get("tools", "").split(",") if t.strip()}


def rewrite(text: str, replacements: tuple[tuple[str, str], ...]) -> str:
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def command_skill(src: Path) -> str:
    """SKILL.md for a Claude slash command.

    The description comes from the title line (``# /name - Description``);
    the Claude model hint (``**Model:** ...``) is dropped.
    """
    lines = src.read_text(encoding="utf-8").splitlines()
    title = lines[0] if lines and lines[0].startswith("# ") else ""
    description = title.split(" - ", 1)[1].strip() if " - " in title else src.stem
    body = "\n".join(line for line in lines[1 if title else 0:]
                     if not line.startswith("**Model:**")).strip()
    return (f"---\nname: {src.stem}\ndescription: {json.dumps(description)}\n---\n\n"
            f"# {description}\n\n{body}\n")
