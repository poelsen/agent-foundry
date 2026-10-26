"""Shipped instructions must not shout.

Current models follow instructions literally: "MANDATORY", "ALWAYS launch"
and "Use PROACTIVELY" read as compulsions and made a downstream project's
model over-spawn agents and over-test (issue #21). These tests keep such
words out of every rule the foundry ships, out of the AGENTS.md block it
renders, and out of agent description fields (which Claude Code uses to
decide when to delegate on its own). Prose only: code fences are skipped,
since examples quote what they must.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from foundry import shared  # noqa: E402
from foundry.adapters import Selections  # noqa: E402
from foundry.registry import BASE_RULES, MODULAR_RULES  # noqa: E402

SHOUTED = re.compile(
    r"\b(MANDATORY|ALWAYS|NEVER|PROACTIVELY|IMMEDIATELY|MUST|CRITICAL|REQUIRED"
    r"|STOP|BLOCK|ONLY|NOT|ALL|ANY)\b"
)
_FENCE = re.compile(r"\s*(```|~~~)")


def shouted_lines(text: str) -> list[str]:
    """Lines outside code fences that contain a shouted imperative."""
    hits, fence = [], None
    for line in text.split("\n"):
        if m := _FENCE.match(line):
            fence = None if fence == m.group(1) else fence or m.group(1)
        elif fence is None and SHOUTED.search(line):
            hits.append(line.strip())
    return hits


def _rule_files() -> list[Path]:
    base = [p for p in (REPO_ROOT / "common" / "rules").glob("*.md") if p.name != "README.md"]
    library = list((REPO_ROOT / "common" / "rule-library").glob("*/*.md"))
    return sorted(base + library)


@pytest.mark.parametrize("path", _rule_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_rule_does_not_shout(path: Path):
    assert shouted_lines(path.read_text(encoding="utf-8")) == []


def test_rendered_block_does_not_shout():
    """Every portable rule, rendered the way projects receive it."""
    sel = Selections(
        base=list(BASE_RULES),
        modular={cat: list(rules) for cat, rules in MODULAR_RULES.items()},
        agents=[], skills=[], learned=[], hooks=[], plugins=[], mcp_servers=[],
        langs=set(MODULAR_RULES["lang"]), project_name="demo", version="9999.99.99",
    )
    block, _ = shared.render_agents_block(sel, budget=10**7)
    assert shouted_lines(block) == []


@pytest.mark.parametrize(
    "path", sorted((REPO_ROOT / "cli" / "claude" / "agents").glob("*.md")), ids=lambda p: p.stem,
)
def test_agent_description_does_not_shout(path: Path):
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^description:\s*(.*)$", text, flags=re.M)
    assert m, f"{path.name} has no description field"
    assert not SHOUTED.search(m.group(1)), m.group(1)


def test_shouted_lines_skips_code_fences():
    text = "prose\n```\nMUST = 1\n```\nmore prose\n~~~\nALWAYS\n~~~\n"
    assert shouted_lines(text) == []
    assert shouted_lines("You MUST\n") == ["You MUST"]
