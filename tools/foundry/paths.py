"""Path resolution and module-level path constants for foundry.

REPO_ROOT resolution:

The foundry package lives at ``<repo>/tools/foundry/``. ``paths.py`` is at
``<repo>/tools/foundry/paths.py`` so the repo root is three parents up.

In source mode the package is imported directly from the clone, so
``Path(__file__).resolve().parent.parent.parent`` is the foundry repo root.

In tarball mode the bootstrap shim (``tools/setup.py``) extracts a sibling
``foundry.tar.gz`` to a tempdir and inserts the extracted ``tools/`` dir on
``sys.path`` BEFORE importing the package. By that point the package lives at
``<extracted-root>/tools/foundry/``, so the same three-parents-up rule yields
``<extracted-root>`` — the correct REPO_ROOT for that run. The shim owns all
tarball extraction; this module never touches archives.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

# Tarball-mode flags. Extraction is owned by the bootstrap shim
# (tools/setup.py), which sets these by importing and assigning when it
# extracts a sibling tarball. They remain at their source-mode defaults
# when the package is imported directly from a clone.
_TARBALL_MODE = False
_PAYLOAD_TARBALL: Path | None = None


def _ensure_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 so print() emoji never crash on Windows.

    Fixes issue #26: setup.py uses Unicode characters (✓, ✗, ⚠, em dashes,
    etc.) in print() output. On Windows with a default cp1252 console
    encoding, writing those characters raises UnicodeEncodeError and
    crashes the whole install. Reconfiguring the TextIOWrapper to UTF-8
    with ``errors='replace'`` is a strictly additive fix: it has no effect
    where stdout is already UTF-8 (Linux/macOS/WSL/Windows Terminal), and
    it turns crashes into replacement characters on legacy cp1252 consoles.

    This runs unconditionally at module import time. It's safe because:
      1. ``reconfigure()`` is a no-op if encoding is already UTF-8
      2. Any failure (e.g. stdout is piped to a process that can't be
         reconfigured, or stdout was replaced before import) is swallowed
         — the worst case is a legacy cp1252 crash at first emoji, which
         is the pre-fix baseline
      3. ``errors='replace'`` means worst-case a unicode char becomes "?"
         instead of raising
    """
    for stream in (sys.stdout, sys.stderr):
        enc = getattr(stream, "encoding", None)
        if enc is None or enc.lower() == "utf-8":
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # not a TextIOWrapper (e.g. replaced by a test harness)
        # OSError: underlying buffer not seekable or closed.
        # ValueError: invalid encoding name (shouldn't happen with "utf-8").
        with contextlib.suppress(OSError, ValueError):
            reconfigure(encoding="utf-8", errors="replace")


_ensure_utf8_stdio()


def _resolve_repo_root() -> Path:
    """Resolve REPO_ROOT for both source and tarball modes.

    The bootstrap shim (tools/setup.py) owns all tarball extraction and
    sys.path setup, so by the time this package is imported the foundry
    source tree (source clone or extracted tarball) is laid out as
    ``<root>/tools/foundry/paths.py``. The repo root is therefore always
    three parents up from this file.
    """
    return Path(__file__).resolve().parent.parent.parent


REPO_ROOT = _resolve_repo_root()


# ── CLAUDE.md markers ───────────────────────────────────────────────────

AGENT_FOUNDRY_MARKER_START = "<!-- agent-foundry -->"
AGENT_FOUNDRY_MARKER_END = "<!-- /agent-foundry -->"


# ── Source-dir constants ────────────────────────────────────────────────

AGENTS_DIR = REPO_ROOT / "cli" / "claude" / "agents"
COMMANDS_DIR = REPO_ROOT / "cli" / "claude" / "commands"
LEARNED_SKILLS_DIR = REPO_ROOT / "cli" / "claude" / "skills" / "learned"
MCP_SERVERS_FILE = REPO_ROOT / "common" / "mcp" / "mcp-servers.json"
