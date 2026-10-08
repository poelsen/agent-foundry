# /update-codemaps - Generate/Refresh Architecture Documentation

**Model:** opus (requires architectural judgment)

## Workflow

1. **Detect language**: pyproject.toml (Python), tsconfig.json (TS), CMakeLists.txt (C++), go.mod (Go), Cargo.toml (Rust)

2. **Check staleness**: If codemaps/ exists, read frontmatter `source_hash`, run `git diff <hash>..HEAD -- <files>`. Skip current ones.

3. **Regenerate stale**: Read source, extract purpose/components/API/dependencies/data flow, write 30-50 line codemap.

4. **Write with frontmatter**:
   ```yaml
   ---
   generated: YYYY-MM-DDTHH:MM:SSZ
   source_hash: <commit>
   files_covered: [src/module/*.py]
   ---
   ```

5. **Report**: "X/Y updated, Z current"

## Codemap Format

```markdown
# Module: [name]
**Path:** src/module/ | **Purpose:** [1-2 sentences]

## Key Components
- ClassName — responsibility (file.py:line)

## Public API
- method(args) → return — description

## Dependencies
- module_a — usage

## Data Flow
[1-3 lines]
```

## INDEX.md

Table: Module | Path | Purpose

## Output

`codemaps/` in project root, one file per module, INDEX.md overview.
