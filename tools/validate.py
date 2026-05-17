#!/usr/bin/env python3
"""Validate claude-foundry repo integrity.

Usage:
    python3 tools/validate.py              # Static checks + smoke test
    python3 tools/validate.py --tarball X  # Also validate release tarball
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Import setup.py registries
sys.path.insert(0, str(REPO_ROOT / "tools"))
import setup as setup_module  # noqa: E402


def parse_frontmatter(text: str) -> dict | None:
    """Parse YAML frontmatter between --- delimiters. Returns None if absent."""
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    fm: dict[str, str] = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm


class Validator:
    def __init__(self, repo_root: Path) -> None:
        self.root = repo_root
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks_run = 0

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def check(self, name: str) -> None:
        self.checks_run += 1
        print(f"  [{self.checks_run}] {name}")

    # ── Group 1: Static checks ──────────────────────────────────────

    def check_json_files(self) -> None:
        self.check("JSON validity")
        for rel in ["mcp-configs/mcp-servers.json"]:
            path = self.root / rel
            if not path.exists():
                self.error(f"Missing JSON file: {rel}")
                continue
            try:
                json.loads(path.read_text())
            except json.JSONDecodeError as e:
                self.error(f"Invalid JSON in {rel}: {e}")

    def check_markdown_rules(self) -> None:
        self.check("Markdown: rules")
        for d in [self.root / "rules", self.root / "rule-library"]:
            for md in sorted(d.rglob("*.md")):
                if md.name == "README.md":
                    continue
                text = md.read_text().strip()
                if not text:
                    self.error(f"Empty markdown: {md.relative_to(self.root)}")
                    continue
                first_line = text.lstrip().split("\n", 1)[0]
                if not first_line.startswith("#"):
                    self.error(f"No H1 header: {md.relative_to(self.root)}")

    def check_markdown_commands(self) -> None:
        self.check("Markdown: commands")
        for md in sorted((self.root / "commands").glob("*.md")):
            text = md.read_text().strip()
            if not text:
                self.error(f"Empty command file: {md.name}")
                continue
            first_line = text.lstrip().split("\n", 1)[0]
            if not first_line.startswith("#"):
                self.error(f"No H1 header in command: {md.name}")

    def check_markdown_agents(self) -> None:
        self.check("Markdown: agents (frontmatter)")
        required_keys = {"name", "description", "tools", "model"}
        agents_dir = self.root / "agents"
        if not agents_dir.is_dir():
            self.error("Missing agents/ directory")
            return
        for md in sorted(agents_dir.glob("*.md")):
            text = md.read_text()
            fm = parse_frontmatter(text)
            if fm is None:
                self.error(f"Agent missing frontmatter: {md.name}")
                continue
            missing = required_keys - set(fm.keys())
            if missing:
                self.error(f"Agent {md.name} missing frontmatter keys: {', '.join(sorted(missing))}")

    def check_markdown_skills(self) -> None:
        self.check("Markdown: skills (frontmatter)")
        skills_dir = self.root / "skills"
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name in ("learned", "learned-local"):
                continue
            if skill_dir.name.startswith("_"):
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                self.error(f"Skill directory {skill_dir.name}/ missing SKILL.md")
                continue
            text = skill_md.read_text()
            fm = parse_frontmatter(text)
            if fm is None:
                self.error(f"Skill {skill_dir.name}/SKILL.md missing frontmatter")

    def check_registry_base_rules(self) -> None:
        self.check("Registry: BASE_RULES")
        for rule in setup_module.BASE_RULES:
            path = self.root / "rules" / rule
            if not path.exists():
                self.error(f"BASE_RULES references missing file: rules/{rule}")

    def check_registry_modular_rules(self) -> None:
        self.check("Registry: MODULAR_RULES")
        for category, rules in setup_module.MODULAR_RULES.items():
            for rule in rules:
                path = self.root / "rule-library" / category / rule
                if not path.exists():
                    self.error(f"MODULAR_RULES references missing file: rule-library/{category}/{rule}")

    def check_registry_hooks(self) -> None:
        self.check("Registry: HOOK_SCRIPTS")
        for script in setup_module.HOOK_SCRIPTS:
            path = self.root / "hooks" / "library" / script
            if not path.exists():
                self.error(f"HOOK_SCRIPTS references missing file: hooks/library/{script}")
            elif not os.access(path, os.X_OK):
                self.error(f"Hook script not executable: hooks/library/{script}")

    def check_registry_skills(self) -> None:
        self.check("Registry: SKILLS")
        for skill in setup_module.SKILLS:
            skill_md = self.root / "skills" / skill / "SKILL.md"
            if not skill_md.exists():
                self.error(f"SKILLS references missing: skills/{skill}/SKILL.md")

    def check_review_process_reviewers(self) -> None:
        """Verify reviewer names in review-process skill resolve to real
        agents/skills. Catches typos like 'architect-pyton' in routing tables.
        Skips wildcards (regex `[a-z0-9-]` cannot capture `*`).
        """
        self.check("Review-process reviewer references")
        skill_dir = self.root / "skills" / "review-process"
        if not skill_dir.is_dir():
            return

        backtick = re.compile(r"`([a-z][a-z0-9-]+)`")
        agent_prefixes = (
            "code-reviewer-", "security-reviewer-", "tdd-guide-", "architect-",
            "refactor-cleaner-", "build-error-resolver-", "e2e-test-",
        )
        skill_names = {
            "megamind-deep", "megamind-adversarial",
            "megamind-creative", "megamind-financial",
            "gui-threading", "python-qt-gui",
            "copilot-cli",
        }

        existing_agents = {p.stem for p in (self.root / "agents").glob("*.md")}
        existing_skills = {
            d.name for d in (self.root / "skills").iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        }

        seen: set[tuple[str, str]] = set()
        for md in sorted(skill_dir.rglob("*.md")):
            text = md.read_text()
            for m in backtick.finditer(text):
                token = m.group(1)
                if any(token.startswith(p) and len(token) > len(p)
                       for p in agent_prefixes):
                    key = (md.name, token)
                    if key in seen:
                        continue
                    seen.add(key)
                    if token not in existing_agents:
                        self.error(
                            f"Review-process {md.name}: backticked agent "
                            f"`{token}` has no matching agents/{token}.md"
                        )
                elif token in skill_names:
                    key = (md.name, token)
                    if key in seen:
                        continue
                    seen.add(key)
                    if token not in existing_skills:
                        self.error(
                            f"Review-process {md.name}: backticked skill "
                            f"`{token}` has no matching skills/{token}/SKILL.md"
                        )

    def check_version(self) -> None:
        self.check("Version (file or git tag)")
        ver_path = self.root / "VERSION"
        if ver_path.exists():
            ver = ver_path.read_text().strip()
            if not re.match(r"^\d{4}\.\d{2}\.\d{2}(\.\d+)?$", ver):
                self.error(f"VERSION doesn't match CalVer pattern: '{ver}'")
            return
        # No VERSION file — check git tag
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), "describe", "--tags", "--abbrev=0"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                self.warn("No VERSION file and no git tags — version will be 'dev'")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self.warn("No VERSION file and git not available — version will be 'dev'")

    def check_setup_parse(self) -> None:
        self.check("setup.py syntax")
        setup_path = self.root / "tools" / "setup.py"
        try:
            compile(setup_path.read_text(), str(setup_path), "exec")
        except SyntaxError as e:
            self.error(f"setup.py syntax error: {e}")

    def check_setup_version(self) -> None:
        self.check("setup.py version command")
        result = subprocess.run(
            [sys.executable, str(self.root / "tools" / "setup.py"), "version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            self.error(f"setup.py version failed (rc={result.returncode}): {result.stderr.strip()}")

    # ── Group 2: Smoke test ──────────────────────────────────────────

    def check_smoke_test(self) -> None:
        self.check("Smoke test: setup.py init --non-interactive")
        tmpdir = Path(tempfile.mkdtemp(prefix="claude-foundry-test-"))
        try:
            result = subprocess.run(
                [sys.executable, str(self.root / "tools" / "setup.py"),
                 "init", str(tmpdir), "--non-interactive"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                self.error(f"Smoke test failed (rc={result.returncode}):\n{result.stderr}\n{result.stdout}")
                return

            claude_dir = tmpdir / ".claude"

            # VERSION
            ver_file = claude_dir / "VERSION"
            if not ver_file.exists():
                self.error("Smoke: .claude/VERSION not created")
            else:
                ver = ver_file.read_text().strip()
                if ver != "dev" and not re.match(r"^\d{4}\.\d{2}\.\d{2}(\.\d+)?$", ver):
                    self.error(f"Smoke: .claude/VERSION invalid: '{ver}'")

            # setup-manifest.json
            manifest_file = claude_dir / "setup-manifest.json"
            if not manifest_file.exists():
                self.error("Smoke: .claude/setup-manifest.json not created")
            else:
                try:
                    manifest = json.loads(manifest_file.read_text())
                except json.JSONDecodeError as e:
                    self.error(f"Smoke: setup-manifest.json invalid JSON: {e}")
                    manifest = None
                if manifest:
                    required_keys = {"version", "config_repo", "repo_url", "base_rules",
                                     "modular_rules", "hooks", "agents", "skills", "plugins"}
                    missing = required_keys - set(manifest.keys())
                    if missing:
                        self.error(f"Smoke: manifest missing keys: {', '.join(sorted(missing))}")

            # settings.json
            settings_file = claude_dir / "settings.json"
            if not settings_file.exists():
                self.error("Smoke: .claude/settings.json not created")
            else:
                try:
                    json.loads(settings_file.read_text())
                except json.JSONDecodeError as e:
                    self.error(f"Smoke: settings.json invalid JSON: {e}")

            # Rules — non-interactive with no manifest defaults to all base rules
            rules_dir = claude_dir / "rules"
            if not rules_dir.is_dir():
                self.error("Smoke: .claude/rules/ not created")
            else:
                for rule in setup_module.BASE_RULES:
                    if not (rules_dir / rule).exists():
                        self.error(f"Smoke: base rule not deployed: {rule}")

            # Commands
            commands_dir = claude_dir / "commands"
            if not commands_dir.is_dir():
                self.error("Smoke: .claude/commands/ not created")
            else:
                source_cmds = {f.name for f in (self.root / "commands").glob("*.md")}
                deployed_cmds = {f.name for f in commands_dir.glob("*.md")}
                # Commands gated behind an OPTIONAL_FEATURES toggle (e.g.
                # commands/delegate.md under "minimax-delegate") aren't
                # expected to deploy — features default OFF in the smoke run.
                gated_cmds: set[str] = set()
                feature_paths = getattr(setup_module, "FEATURE_PATHS", {})
                for paths in feature_paths.values():
                    for rel in paths:
                        if rel.startswith("commands/") and rel.endswith(".md"):
                            gated_cmds.add(Path(rel).name)
                missing_cmds = (source_cmds - deployed_cmds) - gated_cmds
                if missing_cmds:
                    self.error(f"Smoke: commands not deployed: {', '.join(sorted(missing_cmds))}")

            # CLAUDE.md
            if not (tmpdir / "CLAUDE.md").exists():
                self.error("Smoke: CLAUDE.md not created at project root")

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ── Group 3: Tarball validation ──────────────────────────────────

    def check_tarball(self, tarball_path: Path) -> None:
        self.check(f"Tarball: {tarball_path.name}")
        if not tarball_path.exists():
            self.error(f"Tarball not found: {tarball_path}")
            return

        tmpdir = Path(tempfile.mkdtemp(prefix="claude-foundry-tarball-"))
        try:
            with tarfile.open(tarball_path, "r:gz") as tf:
                tf.extractall(tmpdir)

            # Find the extracted directory (should be claude-foundry-<version>/)
            extracted = list(tmpdir.iterdir())
            if len(extracted) != 1 or not extracted[0].is_dir():
                self.error("Tarball should contain exactly one top-level directory")
                return
            root = extracted[0]

            # Check expected contents
            expected = ["VERSION", "rules", "rule-library", "agents", "commands",
                        "skills", "hooks", "mcp-configs", "tools/setup.py"]
            for item in expected:
                path = root / item
                if not path.exists():
                    self.error(f"Tarball missing: {item}")

            # VERSION in tarball must be valid CalVer
            ver_file = root / "VERSION"
            if ver_file.exists():
                ver = ver_file.read_text().strip()
                if not re.match(r"^\d{4}\.\d{2}\.\d{2}(\.\d+)?$", ver):
                    self.error(f"Tarball VERSION doesn't match CalVer: '{ver}'")

            # Smoke test from tarball
            self.check("Tarball smoke test")
            project_dir = Path(tempfile.mkdtemp(prefix="claude-foundry-tarball-proj-"))
            try:
                result = subprocess.run(
                    [sys.executable, str(root / "tools" / "setup.py"),
                     "init", str(project_dir), "--non-interactive"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    self.error(f"Tarball smoke test failed (rc={result.returncode}):\n{result.stderr}\n{result.stdout}")
                elif not (project_dir / ".claude" / "VERSION").exists():
                    self.error("Tarball smoke test: .claude/VERSION not created")
            finally:
                shutil.rmtree(project_dir, ignore_errors=True)

        except tarfile.TarError as e:
            self.error(f"Tarball extraction failed: {e}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ── Runner ───────────────────────────────────────────────────────

    def run_all(self, tarball: Path | None = None) -> bool:
        print("=== Static checks ===")
        self.check_json_files()
        self.check_markdown_rules()
        self.check_markdown_commands()
        self.check_markdown_agents()
        self.check_markdown_skills()
        self.check_registry_base_rules()
        self.check_registry_modular_rules()
        self.check_registry_hooks()
        self.check_registry_skills()
        self.check_review_process_reviewers()
        self.check_version()
        self.check_setup_parse()
        self.check_setup_version()

        print("\n=== Smoke test ===")
        self.check_smoke_test()

        if tarball:
            print("\n=== Tarball validation ===")
            self.check_tarball(tarball)

        # Summary
        print(f"\n{'=' * 40}")
        if self.errors:
            print(f"FAILED: {len(self.errors)} error(s), {self.warnings and len(self.warnings) or 0} warning(s)")
            for e in self.errors:
                print(f"  ERROR: {e}")
            for w in self.warnings:
                print(f"  WARN:  {w}")
            return False
        else:
            print(f"OK: {self.checks_run} checks passed, {len(self.warnings)} warning(s)")
            for w in self.warnings:
                print(f"  WARN:  {w}")
            return True


def main() -> None:
    tarball = None
    args = sys.argv[1:]
    if "--tarball" in args:
        idx = args.index("--tarball")
        if idx + 1 < len(args):
            tarball = Path(args[idx + 1]).resolve()
        else:
            print("Error: --tarball requires a path argument")
            sys.exit(1)

    v = Validator(REPO_ROOT)
    ok = v.run_all(tarball=tarball)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
