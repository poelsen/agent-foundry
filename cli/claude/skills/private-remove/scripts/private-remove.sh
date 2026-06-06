#!/usr/bin/env bash
set -euo pipefail

# /private-remove <prefix> — Remove a private config source by prefix
# Deletes all {prefix}-* files and removes the source from manifest

PREFIX="${1:-}"

if [[ -z "$PREFIX" ]]; then
    echo "Usage: /private-remove <prefix>"
    echo ""
    echo "Run /private-list to see registered sources."
    exit 1
fi

MANIFEST=".claude/setup-manifest.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "No setup manifest found at $MANIFEST"
    exit 1
fi

# Find Python — probe by execution, not PATH (Windows MS Store stub is on PATH
# but errors out). Validates user-supplied PYTHON too.
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
        PYTHON="uv run python"
    fi
fi
if [[ -z "${PYTHON:-}" ]]; then
    echo "Error: No working Python 3.11+ interpreter found." >&2
    exit 1
fi

# Verify prefix exists in manifest. Pass MANIFEST and PREFIX via env vars to
# avoid shell-to-Python injection when paths or prefixes contain apostrophes
# or other Python syntax.
FOUND=$(MANIFEST_PATH="$MANIFEST" PRIVATE_PREFIX="$PREFIX" $PYTHON -c "
import json, sys, os
m = json.load(open(os.environ['MANIFEST_PATH']))
sources = m.get('private_sources', [])
target = os.environ['PRIVATE_PREFIX']
for s in sources:
    if s.get('prefix') == target:
        print('found')
        sys.exit(0)
print('not_found')
" 2>&1)

if [[ "$FOUND" != "found" ]]; then
    echo "No private source with prefix '$PREFIX' found."
    echo ""
    echo "Run /private-list to see registered sources."
    exit 1
fi

echo "Removing private source: $PREFIX"

# Remove prefixed files from all component dirs
REMOVED=0
for dir in .claude/rules .claude/agents .claude/commands; do
    if [[ -d "$dir" ]]; then
        for f in "$dir"/"${PREFIX}"-*; do
            if [[ -f "$f" ]]; then
                rm "$f"
                echo "  Removed: $f"
                REMOVED=$((REMOVED + 1))
            fi
        done
    fi
done

# Remove prefixed skill directories
if [[ -d ".claude/skills" ]]; then
    for d in .claude/skills/"${PREFIX}"-*/; do
        if [[ -d "$d" ]]; then
            rm -rf "$d"
            echo "  Removed: $d"
            REMOVED=$((REMOVED + 1))
        fi
    done
fi

# Remove prefixed hook scripts
if [[ -d ".claude/hooks/library" ]]; then
    for f in .claude/hooks/library/"${PREFIX}"-*; do
        if [[ -f "$f" ]]; then
            rm "$f"
            echo "  Removed: $f"
            REMOVED=$((REMOVED + 1))
        fi
    done
fi

# Update manifest — remove the source entry (env-var passing, as above)
MANIFEST_PATH="$MANIFEST" PRIVATE_PREFIX="$PREFIX" $PYTHON -c "
import json, os
path = os.environ['MANIFEST_PATH']
target = os.environ['PRIVATE_PREFIX']
m = json.load(open(path))
sources = m.get('private_sources', [])
m['private_sources'] = [s for s in sources if s.get('prefix') != target]
if not m['private_sources']:
    del m['private_sources']
with open(path, 'w') as f:
    json.dump(m, f, indent=2)
    f.write('\n')
"

echo ""
echo "Removed $REMOVED files/directories with prefix '$PREFIX'"
echo "Manifest updated."
