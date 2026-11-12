"""The Claude adapter merges the foundry's settings into .claude/settings.json;
keys the project added there survive an update."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from foundry.deploy import (
    generate_settings_json,
    merge_settings_json,
    write_settings_json,
)
from foundry.orchestrator import cmd_init

GUARD_CMD = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/bash-output-guard.py'
RUFF_CMD = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/library/ruff-format.sh'


def _commands(settings: dict, event: str) -> list[str]:
    return [h["command"] for group in settings["hooks"].get(event, []) for h in group["hooks"]]


def test_project_keys_survive():
    existing = {"permissions": {"allow": ["Bash(uv run pytest:*)"]},
                "env": {"TEAM": "1"}, "model": "opus",
                "attribution": {"commit": "x", "issue": "kept"}}
    merged, removed = merge_settings_json(existing, generate_settings_json([], []), set())
    assert merged["permissions"] == existing["permissions"]
    assert merged["env"] == {"TEAM": "1"} and merged["model"] == "opus"
    assert merged["attribution"] == {"commit": "", "pr": "", "sessionUrl": False, "issue": "kept"}
    assert merged["bashOutputMaxChars"] == 16_000
    assert removed == []


def test_worktree_base_defaults_to_head_unless_the_project_chose():
    generated = generate_settings_json([], [])
    merged, _ = merge_settings_json({}, generated, set())
    assert merged["worktree"] == {"baseRef": "head"}
    chosen = {"worktree": {"baseRef": "fresh", "other": "kept"}}
    merged, _ = merge_settings_json(chosen, generated, set())
    assert merged["worktree"] == chosen["worktree"]


def test_project_hooks_survive_and_foundry_hooks_are_reconciled():
    own_group = {"matcher": "Bash", "hooks": [{"type": "command", "command": "./scripts/audit.sh"}]}
    mixed_group = {"matcher": "Edit|MultiEdit|Write", "hooks": [
        {"type": "command", "command": RUFF_CMD},
        {"type": "command", "command": "./scripts/lint-extra.sh"}]}
    retired_group = {"matcher": "Edit", "hooks": [
        {"type": "command", "command": ".claude/hooks/library/retired-check.sh"}]}
    existing = {"hooks": {"PreToolUse": [own_group],
                          "PostToolUse": [mixed_group, retired_group],
                          "Stop": [{"hooks": [{"type": "command", "command": "./scripts/done.sh"}]}]}}

    merged, _ = merge_settings_json(existing, generate_settings_json(["ruff-format.sh"], []), set())

    assert _commands(merged, "PreToolUse") == ["./scripts/audit.sh", GUARD_CMD]
    assert _commands(merged, "PostToolUse") == ["./scripts/lint-extra.sh", RUFF_CMD]
    assert _commands(merged, "Stop") == ["./scripts/done.sh"]


def test_only_owned_plugins_are_disabled():
    existing = {"enabledPlugins": {
        "pyright-lsp@claude-plugins-official": True,     # enabled by the foundry last run
        "code-review@claude-plugins-official": True,     # retired foundry plugin
        "clangd-lsp@claude-plugins-official": True,      # the user's own choice
        "team-tools@acme-marketplace": True}}
    generated = generate_settings_json([], ["rust-analyzer-lsp"])
    merged, removed = merge_settings_json(existing, generated, {"pyright-lsp", "code-review"})
    assert merged["enabledPlugins"] == {
        "clangd-lsp@claude-plugins-official": True,
        "team-tools@acme-marketplace": True,
        "rust-analyzer-lsp@claude-plugins-official": True}
    assert removed == ["code-review@claude-plugins-official", "pyright-lsp@claude-plugins-official"]


def test_merge_is_idempotent():
    existing = {"env": {"A": "1"},
                "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
                    {"type": "command", "command": "./scripts/audit.sh"}]}]}}
    generated = generate_settings_json(["ruff-format.sh"], ["pyright-lsp"])
    once, _ = merge_settings_json(existing, generated, set())
    twice, _ = merge_settings_json(once, generated, {"pyright-lsp"})
    assert twice == once


def test_unparsable_file_is_left_alone(tmp_path: Path, capsys):
    path = tmp_path / ".claude" / "settings.json"
    path.parent.mkdir()
    path.write_text("{ not json")
    assert not write_settings_json(tmp_path, [], [], set())
    assert path.read_text() == "{ not json"
    assert "doesn't parse" in capsys.readouterr().out


def test_update_keeps_team_settings(tmp_path: Path):
    """End to end: a second init keeps what the team added after the first."""
    (tmp_path / "app.py").write_text("print(1)\n")
    assert cmd_init(tmp_path, interactive=False, clis=["claude"])
    path = tmp_path / ".claude" / "settings.json"
    settings = json.loads(path.read_text())
    settings["permissions"] = {"allow": ["Bash(uv run pytest:*)"]}
    settings["env"] = {"TEAM": "1"}
    path.write_text(json.dumps(settings, indent=2))

    assert cmd_init(tmp_path, interactive=False, clis=["claude"])

    after = json.loads(path.read_text())
    assert after["permissions"] == {"allow": ["Bash(uv run pytest:*)"]}
    assert after["env"] == {"TEAM": "1"}
    assert _commands(after, "PreToolUse") == [GUARD_CMD]
    assert ".claude/settings.local.json" in (tmp_path / ".gitignore").read_text()
