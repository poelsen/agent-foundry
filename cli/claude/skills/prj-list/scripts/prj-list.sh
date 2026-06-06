#!/usr/bin/env bash
# prj-list.sh — List all named projects with status and resume commands.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
PRJS_DIR="$PROJECT_ROOT/.claude/prjs"

if [[ ! -d "$PRJS_DIR" ]] || [[ -z "$(ls -A "$PRJS_DIR"/*.md 2>/dev/null)" ]]; then
    echo "No projects found."
    echo "Use /prj-new <name> to create one."
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

# Collect and sort by updated date (newest first)
FILES=()
while IFS= read -r f; do
    FILES+=("$f")
done < <(ls -1t "$PRJS_DIR"/*.md 2>/dev/null)

if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "No projects found."
    echo "Use /prj-new <name> to create one."
    exit 0
fi

printf "%-20s %-10s %-18s %s\n" "PROJECT" "STATUS" "UPDATED" "RESUME"
printf "%-20s %-10s %-18s %s\n" "-------" "------" "-------" "------"

for f in "${FILES[@]}"; do
    name=$(basename "$f" .md)
    status=$(parse_field "$f" "status")
    updated=$(parse_field "$f" "updated")
    session_id=$(parse_field "$f" "session_id")
    short_id="${session_id:0:8}"

    resume_cmd=""
    if [[ -n "$short_id" && "$short_id" != "unknown" ]]; then
        resume_cmd="claude -r $short_id"
    fi

    printf "%-20s %-10s %-18s %s\n" "$name" "${status:-unknown}" "${updated:--}" "$resume_cmd"
done

echo ""
echo "${#FILES[@]} project(s)."
echo "Commands: /prj-new <name>  |  /prj-resume <name>  |  /prj-pause <name>"
