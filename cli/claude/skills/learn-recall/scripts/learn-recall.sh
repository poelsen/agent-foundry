#!/usr/bin/env bash
# learn-recall.sh — Search and list learned skill patterns.
# Usage: learn-recall.sh [keyword] [project_dir]
set -euo pipefail

KEYWORD=""
PROJECT_DIR=""

# Parse arguments
for arg in "$@"; do
    if [[ -z "$PROJECT_DIR" && -d "$arg/.claude" ]]; then
        PROJECT_DIR="$arg"
    elif [[ -z "$KEYWORD" ]]; then
        KEYWORD="$arg"
    fi
done

PROJECT_DIR="${PROJECT_DIR:-$PWD}"
SHARED_DIR="$PROJECT_DIR/.claude/skills/learned"
LOCAL_DIR="$PROJECT_DIR/.claude/skills/learned-local"

# Collect all skill files
FILES=()
SOURCES=()

if [[ -d "$SHARED_DIR" ]]; then
    while IFS= read -r -d '' f; do
        FILES+=("$f")
        SOURCES+=("shared")
    done < <(find "$SHARED_DIR" -name "*.md" -type f -print0 2>/dev/null | sort -z)
fi

if [[ -d "$LOCAL_DIR" ]]; then
    while IFS= read -r -d '' f; do
        FILES+=("$f")
        SOURCES+=("local")
    done < <(find "$LOCAL_DIR" -name "*.md" -type f -print0 2>/dev/null | sort -z)
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "No learned skills found."
    echo "Use /learn to extract patterns from your session."
    exit 0
fi

# Extract category from path (parent directory name)
get_category() {
    basename "$(dirname "$1")"
}

# Extract first line of ## Problem section as description
get_description() {
    local file="$1"
    awk '/^## Problem/{getline; while(/^[[:space:]]*$/) getline; gsub(/^[[:space:]]+/, ""); print; exit}' "$file"
}

if [[ -z "$KEYWORD" ]]; then
    # ── List mode ──
    echo "## Learned Skills"
    echo ""

    CURRENT_CAT=""
    for i in "${!FILES[@]}"; do
        f="${FILES[$i]}"
        src="${SOURCES[$i]}"
        cat=$(get_category "$f")
        name=$(basename "$f" .md)
        desc=$(get_description "$f")

        if [[ "$cat" != "$CURRENT_CAT" ]]; then
            [[ -n "$CURRENT_CAT" ]] && echo ""
            echo "### $cat/"
            CURRENT_CAT="$cat"
        fi

        local_tag=""
        [[ "$src" == "local" ]] && local_tag="  [local]"
        echo "- **$name** — ${desc:-No description}${local_tag}"
    done
else
    # ── Search mode ──
    MATCHES=()
    for i in "${!FILES[@]}"; do
        if grep -qil "$KEYWORD" "${FILES[$i]}" 2>/dev/null; then
            MATCHES+=("$i")
        fi
    done

    if [[ ${#MATCHES[@]} -eq 0 ]]; then
        echo "No learned skills matching '$KEYWORD'."
        echo "Use /learn-recall to see all available skills."
        exit 0
    fi

    echo "## Skills matching '$KEYWORD'"
    echo ""

    for idx in "${MATCHES[@]}"; do
        f="${FILES[$idx]}"
        src="${SOURCES[$idx]}"
        cat=$(get_category "$f")
        name=$(basename "$f" .md)

        local_tag=""
        [[ "$src" == "local" ]] && local_tag=" [local]"

        echo "### $cat/$name${local_tag}"
        echo ""
        # Show content (skip the title line)
        tail -n +2 "$f"
        echo ""
        echo "---"
        echo ""
    done
fi
