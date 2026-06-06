#!/usr/bin/env bash
set -euo pipefail

# /private-list — List registered private config sources
# Reads private_sources from .claude/setup-manifest.json

MANIFEST=".claude/setup-manifest.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "No setup manifest found at $MANIFEST"
    exit 0
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

# Extract private_sources array using python (available everywhere setup.py runs)
# Pass MANIFEST via env var to avoid shell-to-Python injection on paths with
# apostrophes or other Python syntax.
SOURCES=$(MANIFEST_PATH="$MANIFEST" $PYTHON -c "
import json, sys, os
try:
    m = json.load(open(os.environ['MANIFEST_PATH']))
except (json.JSONDecodeError, FileNotFoundError):
    sys.exit(0)
sources = m.get('private_sources', [])
if not sources:
    print('No private sources registered.')
    sys.exit(0)
print(f'{len(sources)} private source(s) registered:')
print()
for s in sources:
    path = s.get('path', '?')
    prefix = s.get('prefix', '?')
    exists = os.path.isdir(path)
    status = 'OK' if exists else 'MISSING'
    # Count deployed items
    counts = []
    for key in ['rules', 'commands', 'skills', 'agents', 'hooks']:
        items = s.get(key, [])
        if items:
            counts.append(f'{len(items)} {key}')
    count_str = ', '.join(counts) if counts else 'no items'
    print(f'  [{prefix}] {path}')
    print(f'    Status: {status}')
    print(f'    Deployed: {count_str}')
    # List individual items
    for key in ['rules', 'commands', 'skills', 'agents', 'hooks']:
        items = s.get(key, [])
        for item in items:
            print(f'      {key}: {prefix}-{item}')
    print()
" 2>&1)

echo "$SOURCES"
