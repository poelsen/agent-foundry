#!/usr/bin/env bash
# update-foundry.sh — Deterministic update script for agent-foundry configuration.
# Usage: update-foundry.sh [--check] [--interactive] [project_dir]
#
# Per-project payload model: the foundry release is shipped as a tarball
# at <project>/.foundry/foundry.tar.gz with a sibling setup.py extracted
# from it. setup.py detects the sibling tarball at runtime, extracts to
# a tempdir, and cleans up on exit — nothing under .claude/ that Claude
# could traverse and find duplicates of.
set -euo pipefail

CHECK_ONLY=false
INTERACTIVE_FLAG="--non-interactive"

# Parse flags
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --check) CHECK_ONLY=true ;;
        --interactive) INTERACTIVE_FLAG="" ;;
        *) ARGS+=("$arg") ;;
    esac
done

# pwd -W returns Windows-style paths under MSYS/git-bash so Python (Windows
# native) can open them; plain pwd returns MSYS paths like /d/... which break.
# On Linux/macOS pwd -W fails, and we fall back to pwd.
PROJECT_DIR="$(cd "${ARGS[0]:-$PWD}" && { pwd -W 2>/dev/null || pwd; })"
MANIFEST="$PROJECT_DIR/.claude/setup-manifest.json"

# ── Find Python (before any use) ──────────────────────────────────────
# Probe candidates by actually executing them — not just checking PATH — because
# the Windows Microsoft Store stub for python/python3 is on PATH but errors out.
# Also validates user-supplied PYTHON env override (so PYTHON=bogus fails fast).
PROBE='import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
if [[ -n "${PYTHON:-}" ]]; then
    if ! $PYTHON -c "$PROBE" >/dev/null 2>&1; then
        echo "Error: PYTHON=$PYTHON is not a working Python 3.11+ interpreter." >&2
        exit 1
    fi
else
    for candidate in python3 python "py -3"; do
        if $candidate -c "$PROBE" >/dev/null 2>&1; then
            PYTHON="$candidate"
            break
        fi
    done
    if [[ -z "${PYTHON:-}" ]] && command -v uv &>/dev/null; then
        # `uv run python` not `python3` — on Windows, uv's managed Python
        # only provides python.exe, and `python3` falls through to PATH (MS
        # Store stub). `python` works on all platforms.
        PYTHON="uv run python"
    fi
fi
if [[ -z "${PYTHON:-}" ]]; then
    echo "Error: No working Python 3.11+ interpreter found." >&2
    echo "Install Python 3.11+, or set PYTHON=<path> before running." >&2
    echo "On Windows: install from python.org (not the Microsoft Store) or run 'uv python install'." >&2
    exit 1
fi

# ── Read manifest ──────────────────────────────────────────────────────
if [[ ! -f "$MANIFEST" ]]; then
    echo "Error: No manifest found at $MANIFEST"
    echo "Run setup.py init first to configure the project."
    exit 1
fi

CURRENT_VERSION=$(MANIFEST_PATH="$MANIFEST" $PYTHON -c "import json, os; print(json.load(open(os.environ['MANIFEST_PATH']))['version'])")
REPO_URL=$(MANIFEST_PATH="$MANIFEST" $PYTHON -c "import json, os; print(json.load(open(os.environ['MANIFEST_PATH']))['repo_url'])")

echo "Current version: $CURRENT_VERSION"
echo "Repository: $REPO_URL"

# ── Check latest release ───────────────────────────────────────────────
API_URL="https://api.github.com/repos/$REPO_URL/releases/latest"
RELEASE_JSON=$(curl -sL "$API_URL")

LATEST_VERSION=$(echo "$RELEASE_JSON" | $PYTHON -c "import json,sys; print(json.load(sys.stdin)['tag_name'])")
RELEASE_URL=$(echo "$RELEASE_JSON" | $PYTHON -c "import json,sys; print(json.load(sys.stdin)['html_url'])")
# Find the tarball asset specifically (not the latest-alias or other attachments)
ASSET_URL=$(echo "$RELEASE_JSON" | $PYTHON -c "
import json,sys
d = json.load(sys.stdin)
for a in d.get('assets', []):
    if a['name'].endswith('.tar.gz') and 'latest' not in a['name']:
        print(a['browser_download_url'])
        break
")

echo "Latest version: $LATEST_VERSION"
echo "Release: $RELEASE_URL"

if [[ "$CURRENT_VERSION" == "$LATEST_VERSION" ]]; then
    echo ""
    echo "Already up to date."
    exit 0
fi

echo ""
echo "Update available: $CURRENT_VERSION → $LATEST_VERSION"

if [[ "$CHECK_ONLY" == true ]]; then
    exit 0
fi

# ── Download new tarball into <project>/.foundry/ ─────────────────────
if [[ -z "$ASSET_URL" ]]; then
    echo "Error: No download asset found in release."
    exit 1
fi

FOUNDRY_DIR="$PROJECT_DIR/.foundry"
TARBALL="$FOUNDRY_DIR/foundry.tar.gz"
TARBALL_NEW="$FOUNDRY_DIR/foundry.tar.gz.new"
TARBALL_OLD="$FOUNDRY_DIR/foundry.tar.gz.old"
SETUP_PY="$FOUNDRY_DIR/setup.py"
SETUP_PY_OLD="$FOUNDRY_DIR/setup.py.old"

mkdir -p "$FOUNDRY_DIR"

# Clean up leftovers from any prior failed run, and ensure we don't leave
# the staging files behind on this exit either.
rm -f "$TARBALL_NEW" "$TARBALL_OLD" "$SETUP_PY_OLD"
trap 'rm -f "$TARBALL_NEW"' EXIT

echo ""
echo "Downloading $ASSET_URL ..."
curl -sL "$ASSET_URL" -o "$TARBALL_NEW"

# Sanity: extracted tarball must contain tools/setup.py at the top level
# (with one wrapper dir, matching GitHub release tarball convention).
TAR_FLAGS=""
if tar --help 2>&1 | grep -q -- --force-local; then
    TAR_FLAGS="--force-local"
fi
# NOTE: do NOT use `grep -q` here. Under `set -o pipefail`, grep -q exits
# on the first match and closes its stdin — tar then receives SIGPIPE and
# exits non-zero, which pipefail propagates as a pipeline failure. Use
# grep -c (counts all matches, reads entire input) into a variable instead.
setup_count=$(tar $TAR_FLAGS -tzf "$TARBALL_NEW" 2>/dev/null | grep -c '/tools/setup.py$' || true)
if [[ "$setup_count" -eq 0 ]]; then
    echo "Error: downloaded tarball missing tools/setup.py"
    exit 1
fi

# ── Atomic swap: tarball + setup.py ────────────────────────────────────
[[ -f "$TARBALL"  ]] && mv "$TARBALL"  "$TARBALL_OLD"
[[ -f "$SETUP_PY" ]] && mv "$SETUP_PY" "$SETUP_PY_OLD"
mv "$TARBALL_NEW" "$TARBALL"

# Extract just tools/setup.py from the new tarball alongside it. We use
# --strip-components=2 to drop both the version-wrapper dir and "tools/".
tar $TAR_FLAGS -xzf "$TARBALL" -C "$FOUNDRY_DIR" --strip-components=2 \
    --wildcards '*/tools/setup.py'

if [[ ! -f "$SETUP_PY" ]]; then
    echo "Error: failed to extract tools/setup.py from tarball — rolling back"
    [[ -f "$TARBALL_OLD"  ]] && mv "$TARBALL_OLD"  "$TARBALL"
    [[ -f "$SETUP_PY_OLD" ]] && mv "$SETUP_PY_OLD" "$SETUP_PY"
    exit 1
fi

# ── Snapshot old project state ────────────────────────────────────────
CLAUDE_DIR="$PROJECT_DIR/.claude"
OLD_COMMANDS=$(ls "$CLAUDE_DIR/commands/" 2>/dev/null | sort || true)
OLD_RULES=$(ls "$CLAUDE_DIR/rules/" 2>/dev/null | sort || true)
OLD_AGENTS=$(ls "$CLAUDE_DIR/agents/" 2>/dev/null | sort || true)
OLD_SKILLS=$(ls "$CLAUDE_DIR/skills/" 2>/dev/null | sort || true)

# ── Run the new setup.py against the project ──────────────────────────
echo "Applying update..."
echo ""
if ! $PYTHON "$SETUP_PY" init "$PROJECT_DIR" $INTERACTIVE_FLAG; then
    echo ""
    echo "ERROR: setup.py init failed — rolling back to previous version"
    [[ -f "$TARBALL_OLD"  ]] && mv "$TARBALL_OLD"  "$TARBALL"
    [[ -f "$SETUP_PY_OLD" ]] && mv "$SETUP_PY_OLD" "$SETUP_PY"
    exit 1
fi

# Success — wipe backups
rm -f "$TARBALL_OLD" "$SETUP_PY_OLD"

# ── Report changes ─────────────────────────────────────────────────────
NEW_COMMANDS=$(ls "$CLAUDE_DIR/commands/" 2>/dev/null | sort || true)
NEW_RULES=$(ls "$CLAUDE_DIR/rules/" 2>/dev/null | sort || true)
NEW_AGENTS=$(ls "$CLAUDE_DIR/agents/" 2>/dev/null | sort || true)
NEW_SKILLS=$(ls "$CLAUDE_DIR/skills/" 2>/dev/null | sort || true)

echo ""
echo "═══════════════════════════════════════════"
echo "Update complete: $CURRENT_VERSION → $LATEST_VERSION"
echo "═══════════════════════════════════════════"
echo "  Foundry payload pinned at: $FOUNDRY_DIR"
echo "  Manual re-init:            $PYTHON $SETUP_PY init $PROJECT_DIR"
echo ""

CHANGES=false
if [[ "$OLD_COMMANDS" != "$NEW_COMMANDS" ]]; then
    echo "  Commands changed — available immediately"
    CHANGES=true
fi
if [[ "$OLD_RULES" != "$NEW_RULES" ]]; then
    echo "  Rules changed — take effect next interaction"
    CHANGES=true
fi
if [[ "$OLD_AGENTS" != "$NEW_AGENTS" ]]; then
    echo "  Agents changed — load on demand"
    CHANGES=true
fi
if [[ "$OLD_SKILLS" != "$NEW_SKILLS" ]]; then
    echo "  Skills changed — available immediately"
    CHANGES=true
fi
if [[ "$CHANGES" == false ]]; then
    echo "  Version bumped, configuration unchanged"
fi
