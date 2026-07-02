"""Parse SKILL.md files into structured data for validation and evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ParsedSkill:
    """Parsed representation of a SKILL.md file."""

    name: str
    description: str
    path: Path
    model: str | None = None
    extends: str | None = None
    title: str = ""
    body: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    word_count: int = 0


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Extract YAML frontmatter and body from SKILL.md content.

    Returns (frontmatter_dict, body_after_frontmatter).

    The block is parsed with a spec-compliant YAML parser, matching what
    Claude Code does at load time; a looser parse would let CI validate a
    skill whose frontmatter fails to load when deployed.

    Raises:
        ValueError: If the frontmatter block is not valid YAML.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        return {}, content

    fm_text, body = match.group(1), match.group(2)
    try:
        raw = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML frontmatter: {e}") from e
    if raw is None:
        return {}, body
    if not isinstance(raw, dict):
        raise ValueError(f"Frontmatter must be a YAML mapping, got {type(raw).__name__}")
    fm: dict[str, str] = {
        str(key): "" if value is None else str(value).strip()
        for key, value in raw.items()
    }
    return fm, body


def extract_sections(body: str) -> dict[str, str]:
    """Extract markdown sections (## headings) from body text.

    Returns dict mapping heading text to section content (without the heading).
    """
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in body.splitlines():
        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = heading_match.group(1)
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines).strip()

    return sections


def extract_title(body: str) -> str:
    """Extract the H1 title from body text."""
    match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return match.group(1).strip() if match else ""


def parse_skill(path: Path) -> ParsedSkill:
    """Parse a SKILL.md file into a ParsedSkill.

    Args:
        path: Path to the SKILL.md file.

    Raises:
        FileNotFoundError: If path does not exist.
        ValueError: If the frontmatter is invalid YAML or required fields are missing.
    """
    if not path.exists():
        raise FileNotFoundError(f"Skill file not found: {path}")

    content = path.read_text(encoding="utf-8")
    try:
        fm, body = parse_frontmatter(content)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from e

    if "name" not in fm:
        raise ValueError(f"Missing required frontmatter field 'name' in {path}")
    if "description" not in fm:
        raise ValueError(f"Missing required frontmatter field 'description' in {path}")

    sections = extract_sections(body)
    title = extract_title(body)
    word_count = len(body.split())

    return ParsedSkill(
        name=fm["name"],
        description=fm["description"],
        path=path,
        model=fm.get("model"),
        extends=fm.get("extends"),
        title=title,
        body=body,
        sections=sections,
        word_count=word_count,
    )


def discover_skills(skills_dir: Path) -> list[ParsedSkill]:
    """Discover and parse all skills in a directory.

    Looks for directories containing SKILL.md files.
    Skips directories named 'learned' or 'learned-local'.
    """
    skills: list[ParsedSkill] = []
    if not skills_dir.is_dir():
        return skills

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name in ("learned", "learned-local"):
            continue
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            skills.append(parse_skill(skill_file))

    return skills
