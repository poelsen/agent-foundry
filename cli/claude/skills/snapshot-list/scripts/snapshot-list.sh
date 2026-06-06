#!/usr/bin/env bash
# snapshot-list.sh — List all session snapshots with metadata.
# Usage: snapshot-list.sh [project_dir]
set -euo pipefail

PROJECT_DIR="${1:-$PWD}"
SNAPSHOTS_DIR="$PROJECT_DIR/.claude/snapshots"

if [[ ! -d "$SNAPSHOTS_DIR" ]]; then
    echo "No snapshots found."
    echo "Use /snapshot to capture your current session."
    exit 0
fi

# Collect snapshot files (newest first)
FILES=()
while IFS= read -r f; do
    FILES+=("$f")
done < <(ls -1t "$SNAPSHOTS_DIR"/*.md 2>/dev/null)

if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "No snapshots found."
    echo "Use /snapshot to capture your current session."
    exit 0
fi

# Parse YAML frontmatter field
parse_field() {
    local file="$1" field="$2"
    awk -v f="$field" '
        /^---$/ { if (in_front) exit; in_front=1; next }
        in_front && $0 ~ "^"f":" {
            sub("^"f":[[:space:]]*", "")
            gsub(/^["'"'"']|["'"'"']$/, "")
            print
            exit
        }
    ' "$file"
}

echo "## Snapshots"
echo ""
printf "%-38s  %-10s  %s\n" "File" "Status" "Goal"
printf "%-38s  %-10s  %s\n" "----" "------" "----"

for f in "${FILES[@]}"; do
    name=$(basename "$f")
    goal=$(parse_field "$f" "goal")
    status=$(parse_field "$f" "status")
    printf "%-38s  %-10s  %s\n" "$name" "${status:-unknown}" "${goal:-No description}"
done

echo ""
echo "${#FILES[@]} snapshot(s) found."
echo "Use /snapshot-restore to resume from the most recent."
