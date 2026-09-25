# Agent Foundry

> **Early alpha.** Under active development. The current rule set is most mature for **Python** and **PySide6/Qt** projects. Other languages (C, C++, Rust, Go, TypeScript) have base rules but are less battle-tested. Expect breaking changes.

A framework for configuring **coding-agent CLIs** across different project types and programming languages. It provides modular rules, specialized agents, reusable skills, tool hooks, slash commands, and MCP servers — selected per-project based on what you're building, and deployed into each target CLI's native layout.

**Multi-CLI by design.** Artifacts are split by portability:

- **`common/`** — cross-CLI content (coding-standard rules, MCP servers).
- **`cli/<name>/`** — CLI-specific artifacts (e.g. Claude Code's subagents, skills, slash-commands, hooks).

A per-CLI **adapter** renders the selected artifacts into that CLI's conventions. Supported targets today:

| Target | Reads | Gets |
|--------|-------|------|
| **[Claude Code](https://docs.anthropic.com/en/docs/claude-code)** (`claude`) | `AGENTS.md`, `.claude/` | full fidelity — rules, agents, skills, commands, hooks, settings, MCP |
| **[GitHub Copilot CLI](https://github.com/github/copilot-cli)** (`copilot`) | `AGENTS.md`, `.mcp.json`, `.agents/skills/` | coding-standard rules (embedded in the cross-tool [`AGENTS.md`](https://agents.md)), MCP servers (workspace `.mcp.json`), and portable skills as native `SKILL.md` skills |
| **[OpenAI Codex CLI](https://github.com/openai/codex)** (`codex`) | `AGENTS.md`, `.agents/skills/`, `.codex/` | coding-standard rules (`AGENTS.md`), portable skills plus portable commands (`update-codemaps`) as skills, subagents as `.codex/agents/*.toml`, MCP servers in `.codex/config.toml`, formatter hooks in `.codex/hooks.json` |
| **[Google Antigravity CLI](https://antigravity.google)** (`agy`) | `AGENTS.md`, `.agents/` | coding-standard rules (`AGENTS.md`, overflow rules in `.agents/rules/` load natively), portable skills and commands in `.agents/skills/`, subagents as `.agents/agents/*.md`, MCP servers in `.agents/mcp_config.json`, formatter hooks in `.agents/hooks.json` |

Pick targets with `--clis claude,copilot,codex,agy` (or the interactive menu, which comes first so later menus only offer what the chosen CLIs can use). Selected items a CLI can't consume (Copilot has no subagent/hook equivalent; Claude-only skills and rules) are listed in a "Not deployed" report at the end of the run, never silently dropped.

**Shared outputs.** Files that several CLIs read — `AGENTS.md`, `.agents/skills/`, `.mcp.json` — are written once per run for all selected targets, not once per adapter:

- **`AGENTS.md`** is every CLI's instructions file, Claude Code's included — see [AGENTS.md Convention](#agentsmd-convention). It gets a marker-wrapped block with the portable coding-standard rules (Claude-only rules such as `agents.md`, `hooks.md`, `performance.md` go to `.claude/rules/` instead, which Claude Code loads alongside `AGENTS.md`). The block is capped at 20 KB because other CLIs silently truncate large instruction files (Antigravity at 24,000 bytes per file, Codex at 32 KiB in total). Rules that don't fit go to `.agents/rules/foundry-<rule>.md` — with Antigravity `trigger:` frontmatter, so Antigravity loads them natively — and `AGENTS.md` points to them.
- **`.agents/skills/`** is the cross-vendor skill root (Copilot CLI, Codex and Antigravity all load it). Only portable skills go there — megamind ×4, `clickhouse-io`, `gui-threading`, `python-qt-gui`, `writer`, `humanizer`, `update-foundry`, the cross-model CLI references `copilot-cli`, `codex-cli`, `agy-cli`, and `delegate` (see [Delegation](#delegation)) — plus the portable commands (`update-codemaps`, `update-foundry-check`, `update-foundry-interactive`) converted to skills. Deploying adapts them without touching the Claude sources: Claude-only frontmatter (`model`, `allowed-tools`) is dropped, `.claude/skills/` paths and `Skill(x)` calls are rewritten, and a `SKILL.md` over 8 KB (Codex's limit for an explicitly invoked skill) becomes a short pointer to the unchanged text in `SKILL.full.md`. Skills tied to Claude-only state — `prj-*` (Claude session ids), `snapshot-list`, `learn`/`learn-recall`, `private-*`, `review-process` — stay Claude Code-only for now.
- `.agents/` is shared with other tools, so every file the foundry writes there carries an ownership marker and updates only ever prune marked content.

**Codex specifics.** Codex reads `AGENTS.md` and `.agents/skills/` in any project, but everything under `.codex/` (agents, MCP servers, hooks) only once the project is trusted — setup prints how to trust it (`codex` → accept the prompt, or `[projects."<path>"] trust_level = "trusted"` in `~/.codex/config.toml`). Hooks additionally stay inert until you approve each one in Codex's `/hooks`. The foundry only rewrites its own marked block in `.codex/config.toml`, its own agent files and its own hook group, so project settings in those files survive updates. Agents without write tools (architect, code-reviewer) run in Codex's `read-only` sandbox.

**Antigravity specifics.** Antigravity loads a workspace's `.agents/` customizations only once the folder is trusted (run `agy` there once and accept; setup reminds you until it is). Hooks run as the `agent-foundry` entry of `.agents/hooks.json` (set `"enabled": false` there to turn them off — updates keep it); other named hooks are left alone. MCP servers follow the same ownership rule as `.mcp.json` (see Upgrading below). Agents without write tools get an explicit tool list without Antigravity's file-writing tools (reading, searching, and `run_command` where the Claude agent had `Bash`).

## Bootstrap

Requires Python 3.11+. No external dependencies.

### Option A: Download a release

Download the latest tarball from the [Releases page](https://github.com/poelsen/agent-foundry/releases) and extract it:

```bash
tar xzf agent-foundry-*.tar.gz
cd agent-foundry-*
python3 tools/setup.py init /path/to/your/project
```

### Option B: Clone the repo

```bash
git clone https://github.com/poelsen/agent-foundry.git
cd agent-foundry
python3 tools/setup.py init /path/to/your/project
```

### What `setup.py init` does

1. Scans your project for languages (file extensions, config files like `pyproject.toml`, `package.json`, `Cargo.toml`)
2. Presents interactive toggle menus for each component category:
   - **Target CLI(s)** — which coding-agent CLIs to deploy for (Claude Code, Copilot CLI, Codex CLI, Antigravity CLI)
   - **Base rules** — coding style, security, testing, git workflow, etc.
   - **Modular rules** — language tooling, project templates, platform, security
   - **Hooks** — language-specific formatters and type checkers
   - **Agents** — specialized sub-agents matched to your languages
   - **Skills** — domain knowledge modules
   - **Plugins** — LSP servers, workflow plugins
3. Hands the selections to each chosen CLI's adapter, which deploys them into that CLI's layout (`.claude/` for Claude Code, `AGENTS.md` for Copilot, …)
4. Saves selections — including the chosen `clis` — to `.claude/setup-manifest.json` for future updates

Non-interactive: `python3 tools/setup.py init /path/to/project --non-interactive --clis claude,copilot,codex,agy`

## Updating

From any configured project, run the `update-foundry` skill from any target CLI — `/update-foundry` in Claude Code, Copilot CLI and Antigravity, `$update-foundry` in Codex:

```
/update-foundry                # Check for new release, download, and apply
/update-foundry-check          # Just check if an update is available
/update-foundry-interactive    # Full interactive menu to add/change selections
```

`/update-foundry` checks the GitHub releases API, downloads the latest tarball to **`<project>/.foundry/foundry.tar.gz`**, refreshes the sibling `setup.py`, and runs it non-interactively using the saved manifest. Works the same regardless of how you bootstrapped.

### Where foundry lives after install

Every project gets a self-contained payload at:

```
<project>/.foundry/                  # gitignored
├── setup.py                         # extracted from the tarball below
└── foundry.tar.gz                   # the pinned release
```

That's all. Nothing under `.claude/` belongs to foundry's machinery — `.claude/` only contains the artifacts foundry installed for *this project* (commands, skills, agents, rules, hooks). When `setup.py` runs, it detects the sibling tarball, extracts it to a tempdir for the duration of the run, and wipes the tempdir on exit — so Claude never trips over a duplicate copy of the foundry tree while traversing your project.

**Why per-project?** Different projects can be on different foundry versions, and `setup.py` is always matched to the tarball next to it. No user-level cache, no symlinks — one self-contained payload per project. The original bootstrap tarball you downloaded can be deleted as soon as the first install completes; `.foundry/` carries forward.

On every `/update-foundry`, the tarball is replaced atomically (staged as `.foundry/foundry.tar.gz.new`, swapped via `mv` only after a successful setup run; rolled back on failure).

### Manual re-init

To re-run setup.py manually (e.g. to toggle new skill groups, register a private source, or reconfigure):

```bash
python3 <project>/.foundry/setup.py init <project>
```

The post-init summary prints this exact command so you can copy-paste it from your terminal.

For batch updates across all known projects:

```bash
python3 <project>/.foundry/setup.py update-all
```

## AGENTS.md Convention

`AGENTS.md` is the one instructions file for every target CLI. Claude Code reads it too (since v2.1.277), but **only while no `CLAUDE.md` exists** in the project or any directory above it — so the foundry doesn't write a `CLAUDE.md`, and moves an existing one into `AGENTS.md`.

### The agent-foundry block

`AGENTS.md` holds your project's own instructions plus a block wrapped in marker comments (`<!-- agent-foundry -->` ... `<!-- /agent-foundry -->`) that setup rewrites on every run:
- Environment commands for detected languages (setup, test)
- Pointers to `codemaps/INDEX.md` and `docs/`
- The portable coding-standard rules, inlined (up to 20 KB; the rest go to `.agents/rules/` as pointers)

Everything outside the block is yours and is never touched. For a new project, setup creates `AGENTS.md` with just a title and the block.

### Moving off CLAUDE.md

| Existing file | What setup does |
|---------------|-----------------|
| `CLAUDE.md` with the foundry header (current `<!-- agent-foundry -->` or legacy `<!-- claude-foundry -->` markers) | Moves your content (everything outside the header) into `AGENTS.md`, above the foundry block, and deletes `CLAUDE.md` |
| `CLAUDE.md` without the marker | Interactive: asks to **Move** it into `AGENTS.md` or **Quit**. Non-interactive: skips the project, unless `--force` (asks for confirmation, then moves it) |
| Empty `CLAUDE.md` | Deletes it |
| `AGENTS.md` and `CLAUDE.md` linked to each other | Keeps the content as a real `AGENTS.md` and drops the `CLAUDE.md` name |

Portable rules an older foundry deployed to `.claude/rules/` are removed there, since Claude Code would otherwise load each rule twice (once from `AGENTS.md`, once from `.claude/rules/`). Setup warns if `.claude/CLAUDE.md`, `CLAUDE.local.md`, or a `CLAUDE.md` in a parent directory would still hide `AGENTS.md` from Claude Code, and if the installed Claude Code is older than 2.1.277.

### Best practices

- Keep your part of `AGENTS.md` short — project boundaries, conventions the rules don't cover
- Put detailed documentation in `docs/`; other CLIs truncate large instruction files

## Documentation Structure

Claude-foundry recommends a three-tier documentation approach:

| Location | Purpose | Maintained by |
|----------|---------|---------------|
| `AGENTS.md` | Project instructions, environment, coding standards | You + agent-foundry (its block auto-updated) |
| `codemaps/` | Architecture overview per module | `/update-codemaps` (auto-generated) |
| `docs/` | Detailed project documentation | You (manual) |

### AGENTS.md

Keep your part minimal. The agent-foundry block provides:
- Environment commands (setup, test)
- Pointers to `codemaps/INDEX.md` and `docs/`
- The coding standards

Don't put detailed documentation here — it gets out of sync and wastes context.

### codemaps/

Auto-generated architecture docs. Run `/update-codemaps` to create/refresh. Each module gets:
- Purpose and responsibilities
- Key components with file:line references
- Public API surface
- Dependencies and data flow

Claude reads these before modifying unfamiliar code.

### docs/

Your detailed documentation:
- `docs/ARCHITECTURE.md` — design decisions, patterns, rationale
- `docs/DEVELOPMENT.md` — setup guide, workflow, conventions
- `docs/API.md` — detailed API documentation

If setup moved a long `CLAUDE.md` into `AGENTS.md`, move its detailed documentation on to `docs/`.

## Codemaps

Codemaps are auto-generated architecture documentation. Each module gets a markdown file describing key components, public APIs, dependencies, and data flow.

### Using codemaps

1. Run `/update-codemaps` to generate or refresh architecture docs
2. Files are created in `codemaps/` with an `INDEX.md` overview
3. The command checks staleness — only stale codemaps regenerate

### When to update

Run `/update-codemaps` after:
- Adding new modules or packages
- Changing public APIs
- Adding significant new dependencies

Claude automatically reads `codemaps/INDEX.md` before modifying unfamiliar modules (per the `codemaps.md` rule).

## What Gets Installed

Everything is copied into `<project>/.claude/`:

| Component | Source | What it does |
|-----------|--------|--------------|
| **Rules** | `common/rules/` + `common/rule-library/` | Markdown files that instruct the agent on coding standards, security, git workflow, testing methodology (cross-CLI) |
| **Agents** | `cli/claude/agents/` | Specialized sub-agents for TDD, code review, security analysis, architecture design (Claude Code) |
| **Commands** | `cli/claude/commands/` | Slash commands: `/snapshot`, `/learn`, `/learn-recall`, `/update-foundry`, `/update-codemaps` |
| **Skills** | `cli/claude/skills/` | Domain knowledge modules (megamind reasoning, writing pipeline with voice presets, GUI threading, ClickHouse, learned patterns) |
| **Hooks** | `cli/claude/hooks/library/` | Shell scripts that run before/after Claude Code tool calls (formatters, type checkers) |
| **MCP servers** | `common/mcp/` | Cross-vendor MCP configs (deployed to `.mcp.json`) |
| **Plugins** | configured in `settings.json` | LSP servers and workflow plugins (feature-dev, PR review toolkit) |
| **Copilot CLI** | `cli/claude/skills/copilot-cli/` | Thin reference skill for the local GitHub Copilot CLI — lets review-process run non-Claude models. See [Copilot CLI](#copilot-cli). |
| **Delegation** | `cli/claude/skills/delegate/` | Any target CLI hands tasks to any other (Claude Code, Codex, Antigravity, Copilot) as managed jobs: own worktree, policy, audit log, review gate. See [Delegation](#delegation). |

## Rules

Rules are markdown files loaded by Claude Code at session start. They shape how Claude writes code, handles errors, makes commits, and reviews changes.

**Base rules** (`common/rules/`) are recommended for all projects:

- `coding-style.md` — KISS/YAGNI/DRY, small functions, minimal diffs
- `git-workflow.md` — branch naming, commit message format, PR workflow
- `security.md` — mandatory security checks before commits
- `testing.md` — TDD workflow, 80% coverage target
- `architecture.md` — composition over inheritance, module boundaries
- `performance.md` — model selection strategy, context window management
- `agents.md` — when and how to use specialized sub-agents
- `codemaps.md` — architecture documentation system
- `hooks.md` — documents available hooks
- `skills.md` — points Claude to learned patterns when stuck

**Modular rules** (`common/rule-library/`) are selected per-project:

| Category | Examples |
|----------|----------|
| `lang/` | Python, Node.js, Go, Rust, MATLAB |
| `templates/` | Embedded C, Embedded DSP, React App, REST API, Desktop GUI Qt, Library, Scripts, Data Pipeline, Monolith |
| `platform/` | GitHub (auto-detected) |
| `security/` | Sandbox, internal, enterprise |

## Commands

Slash commands are available inside Claude Code after running `setup.py init`:

| Command | What it does |
|---------|--------------|
| `/snapshot` | Captures current session state (task, decisions, files modified, next steps) to a snapshot file. |
| `/snapshot-list` | Lists all snapshots with date, goal, and status. |
| `/snapshot-restore` | Resumes from the most recent snapshot. |
| `/learn` | After solving a non-trivial problem, extracts the pattern into a reusable skill file. See [Learned Skills](#learned-skills). |
| `/learn-recall` | Lists or searches all learned skills. `/learn-recall python` searches for Python-related patterns. |
| `/update-foundry` | Checks GitHub for a newer release and applies it. See [Updating](#updating). |
| `/update-foundry-check` | Checks if an update is available without applying changes. |
| `/update-foundry-interactive` | Full interactive menu to add or change component selections. |
| `/update-codemaps` | Generates or refreshes architecture documentation per module. |
| `/review-process` | Runs a tiered review (risk-tier T0-T4, mode, reviewer routing, finding ledger). See [Review Process](#review-process). |
| `/private-list` | Lists registered private config sources with status. |
| `/private-remove` | Removes a private source by prefix. `/private-remove company` removes all `company-*` files. |
| `/prj-new <name>` | Creates a new named project in `.claude/prjs/<name>.md`. See [Project Management](#project-management). |
| `/prj-list` | Lists all named projects with status and resume commands. |
| `/prj-pause <name>` | Saves current session state and marks the project paused. |
| `/prj-resume <name>` | Loads a project's context and resumes work (suggests `--resume <session_id>`). |
| `/prj-done <name>` | Marks a project complete. |
| `/prj-delete <name>` | Deletes a project file. |

## Agents

Agents are specialized sub-agents that Claude Code launches for specific tasks. During `setup.py init`, agents are selected based on your project's languages.

| Agent | Purpose | Languages |
|-------|---------|-----------|
| `architect-*` | System design and architectural decisions | Python, TypeScript |
| `tdd-guide-*` | Test-driven development (write tests first) | Python, TypeScript |
| `code-reviewer-*` | Code quality, security, maintainability review | Python, TypeScript |
| `security-reviewer-*` | OWASP scanning, vulnerability detection | Python, TypeScript |
| `build-error-resolver-*` | Fix build/lint/type errors with minimal diffs | Python, TypeScript |
| `e2e-test-*` | End-to-end browser or GUI testing | Python (Playwright + pytest-qt), TypeScript (Playwright) |
| `refactor-cleaner-*` | Dead code removal, consolidation | Python, TypeScript |
| `doc-updater` | Documentation and codemap updates | All |

## Hooks

Hooks are shell scripts the coding agent runs after each file edit. The same scripts serve Claude Code (`.claude/settings.json`), Codex (`.codex/hooks.json`) and Antigravity (`.agents/hooks.json`).

### What `setup.py` installs

Hooks are pre-selected by detected language; each script then acts only on its own file types, and only where the project has configured the tool:

| Hook script | Acts on | Runs only when the project has | Effect |
|-------------|---------|--------------------------------|--------|
| `ruff-format.sh` | `.py` | a `[format]` section in `ruff.toml`/`.ruff.toml`, `[tool.ruff.format]` in `pyproject.toml`, or a `ruff-format` pre-commit hook — and no black (`[tool.black]` or a black pre-commit hook) | Formats the edited file |
| `mypy-check.sh` | `.py` | `mypy.ini`, `.mypy.ini`, `[mypy]` in `setup.cfg` or `[tool.mypy]` in `pyproject.toml` | Reports type errors back to the agent |
| `prettier-format.sh` | `.ts`/`.tsx`/`.js`/`.jsx` | a `.prettierrc*`, `prettier.config.*` or `"prettier"` in `package.json` | Formats the edited file |
| `tsc-check.sh` | `.ts`/`.tsx` | `tsconfig.json` and a local `typescript` install (never downloaded) | Reports type errors for the edited file |
| `cargo-check.sh` | `.rs` | `Cargo.toml` | Reports `cargo check` errors |

Every Claude Code project also gets two output limits, whatever hooks are selected. They keep shell output from filling the context, which brings on compaction and loses detail sooner:

- `bashOutputMaxChars: 16000` in `.claude/settings.json`: a command's output beyond 16,000 characters is saved to a file, and Claude gets a 2 KB preview plus the path (Claude Code's default is 30,000). Nothing is lost; Claude greps or reads the file for the rest.
- `.claude/hooks/bash-output-guard.py`, a PreToolUse hook that blocks `cat` of files over 150 lines or 12 KB and points Claude to the Read tool with an offset and limit. Piped, redirected and heredoc uses of `cat` still work.

Other CLIs don't get these; they have no equivalent settings.

The config gate (searched from the edited file up to the repository root) keeps a project that lints with ruff, formats with black, or isn't formatted at all from getting whole-file ruff rewrites. Check hooks never block an edit: their errors reach Claude Code and Codex as additional context — labelled as tool output and capped at 8,000 characters (Antigravity has no such channel, so they go to its hook log). The scripts need `jq`; without it they print a warning and do nothing. On Windows, the Codex and Antigravity hooks need Git Bash's `bash` and `jq` on `PATH` (untested there so far). To turn hooks off, deselect them in `/update-foundry-interactive` — `settings.json` and `hooks.json` entries are regenerated on every update.

### Upgrading from earlier releases

- **Claude Code output limits.** `.claude/settings.json` now caps command output at 16,000 characters (longer output goes to a file with a preview) and blocks `cat` of large files; see [Hooks](#hooks).
- **Hooks now actually run.** Earlier releases wrote a `settings.json` matcher that never matched, so the selected hooks never fired; they now do, gated as above.
- **Copilot skills moved** from `.github/skills/` to the shared `.agents/skills/`; the foundry's four old `megamind-*` copies are removed (only when their `SKILL.md` names that skill).
- **New always-on skills** `codex-cli` and `agy-cli`; `review-process` may route its cross-vendor reviewer through them when those CLIs are installed.
- **`delegate` is now cross-CLI and always-on.** Any target CLI can delegate to any other through one Python runner, `delegate.py` (see [Delegation](#delegation)); the old bash scripts (`run.sh`, `launch.sh`, `worktree.sh`, `lib.sh`, `activate.sh`) and the optional-features menu are gone. Skills the foundry no longer ships aren't removed from existing projects — delete them from `.claude/skills/` by hand. A `.delegate/` line an older release added to `.gitignore` stops `.delegate/policy.json` from being committed; remove it if you want to share a policy.
- **Dropping a target** (e.g. `--clis claude` after `claude,codex`; the interactive menu asks first) removes the foundry's files for it — its agents, hooks and managed config — and the shared `AGENTS.md` block and `.agents/skills/` once no remaining target reads them. Only content the foundry can prove it wrote is removed: a foundry name plus its marker, and never anything through an `AGENTS.md` symlink. An unknown id in `--clis` is an error (exit 2) rather than a silent drop, and `setup.py init` exits 3 when it applies nothing by design (skipped, declined, cancelled) — `/update-foundry` then keeps the previous version.
- **MCP servers are reconciled, not just added.** The foundry records the entries it writes (manifest `deployed_mcp`; after an upgrade, the servers the old manifest selected). A recorded entry that is unchanged — apart from values you filled in, such as API keys, which are kept — is updated, and removed when you deselect it; an entry holding a filled-in key is never removed. Entries you configured yourself are never touched, even if they match the catalog — unless you select that server in the foundry, which adopts an identical entry. Codex keeps a deselected server whose key you filled in by moving it out of the foundry block. A project's own (even empty) `.mcp.json` is never deleted.
- **Codex and Antigravity** load `.codex/` / `.agents/` only in trusted projects; Codex hooks also need approval in `/hooks`.

## Skill Selection (groups, hidden skills, gating)

The skill menu in `setup.py init` presents related skills as **groups**, not individual toggles. Selecting a group toggles all its members together:

| Group | Members | Default |
|-------|---------|---------|
| **Megamind Reasoning** | `megamind-deep`, `megamind-creative`, `megamind-adversarial`, `megamind-financial` | on |
| **Project Management** | `prj-new`, `prj-list`, `prj-pause`, `prj-resume`, `prj-done`, `prj-delete` | on |
| **Writing** | `writer`, `humanizer` | off (opt-in) |

Megamind Reasoning and Project Management are **auto-selected by default**; Writing is **off by default** — toggle it on to deploy the drafting pipeline (`writer` drafts in the author's voice with ten selectable presets, then invokes `humanizer` for the anti-AI audit; the pair deploys together because the hand-off requires both). Individual non-grouped skills (`clickhouse-io`, `gui-threading`, `learn`, `update-foundry`, `snapshot-list`, `private-list`, `private-remove`, `review-process`, `copilot-cli`, etc.) continue to appear as individual entries. A handful — `update-foundry`, `learn`, `learn-recall`, `snapshot-list`, `private-list`, `private-remove`, `review-process`, `copilot-cli`, `codex-cli`, `agy-cli`, and `delegate` — are auto-selected by default; the others are off until explicitly toggled on.

The manifest still stores individual skill names (not group names), so existing projects keep working without migration.

## Learned Skills

Claude Code sessions often produce solutions worth remembering. The `/learn` and `/recall` commands turn these into persistent, searchable knowledge.

### How it works

1. After solving a non-trivial problem, run `/learn`
2. Claude analyzes the session and drafts a skill file (problem → solution → example → when to use)
3. You pick a **category** (e.g. `python`, `debugging`, `pyside6`) and a **save location**:
   - **agent-foundry repo** (default): `cli/claude/skills/learned/<category>/<name>.md` — commit and push to share across machines. Deployed to projects via `setup.py init`.
   - **Project-local**: `.claude/skills/learned-local/<category>/<name>.md` — stays in this project only.
4. When Claude gets stuck on a problem, it checks these directories automatically (via `rules/skills.md`)
5. Run `/recall` to list all learned skills, or `/recall <keyword>` to search

The `cli/claude/skills/learned/` directory starts empty. Categories are created as you learn patterns.

## Private Sources

Private sources let you add company-specific or team-specific rules, commands, skills, agents, and hooks alongside the public agent-foundry config. Register once, and they're automatically re-applied on every `/update-foundry`.

### Directory structure

A private source follows the same layout as agent-foundry:

```
my-company-config/
├── rule-library/          # Rules rendered into AGENTS.md
│   └── templates/
│       └── custom-dsp.md
├── commands/              # Optional slash commands
├── skills/                # Optional skill directories
├── agents/                # Optional agents
└── hooks/
    └── library/           # Optional hooks
```

### Registering a private source

**During interactive init:**
```bash
python3 tools/setup.py init /path/to/project
# ... normal setup ...
# Add a private config source? (path or Enter to skip): /path/to/company-config
# Prefix [company-config]: company
# ... toggle menu for available items ...
```

**Via CLI flags:**
```bash
python3 tools/setup.py init /path/to/project \
  --private /path/to/company-config --prefix company
```

Multiple sources can be registered. Files are deployed with the prefix to avoid collisions (e.g., `company-custom-dsp.md`).

### Managing private sources

| Command | What it does |
|---------|--------------|
| `/private-list` | Show registered sources with deployed file counts |
| `/private-remove <prefix>` | Remove all files with that prefix and unregister |

### How it works

- Selections are saved in `setup-manifest.json` under `"private_sources"`
- `setup.py init --non-interactive` re-deploys from the manifest automatically
- `/update-foundry` calls `setup.py init --non-interactive`, so private sources survive updates
- Foundry's cleanup functions skip private-prefixed files
- Paths are absolute and machine-specific — each team member registers their own local path

## Releases

Every merge to `master` triggers a GitHub Actions workflow that:

1. Computes a [CalVer](https://calver.org/) version (`YYYY.MM.DD`, with `.N` suffix for same-day releases)
2. Creates a git tag
3. Builds a release tarball containing all deployable files
4. Publishes a [GitHub Release](https://github.com/poelsen/agent-foundry/releases) with the tarball attached

## Project Structure

```
agent-foundry/
├── common/                       # Cross-CLI portable artifacts
│   ├── rules/                    # Base rules (selected during init)
│   ├── rule-library/             # Modular rules by category
│   │   ├── lang/                 # Language tooling rules
│   │   ├── templates/            # Project type templates
│   │   ├── platform/             # Platform rules (GitHub)
│   │   └── security/             # Security level rules
│   └── mcp/                      # MCP server configurations
├── cli/                          # CLI-specific artifacts
│   └── claude/                   # Claude Code only
│       ├── agents/               # Sub-agent definitions
│       ├── commands/             # Slash commands
│       ├── skills/               # Domain skills (incl. learned/ via /learn)
│       └── hooks/library/        # Per-language hook scripts
└── tools/
    ├── setup.py                  # Bootstrap shim (source + tarball modes)
    └── foundry/                  # The deployment package
        ├── orchestrator.py       # Selects artifacts, dispatches to adapters
        ├── adapters/             # One per CLI: base, claude, copilot, codex, antigravity
        ├── convert.py            # Parses Claude-format sources for conversion
        ├── shared.py             # Files several CLIs read (AGENTS.md, .agents/, .mcp.json)
        ├── registry.py  detect.py  manifest.py  …
        └── …
```

## Megamind Skills

The megamind skills are reasoning enhancers that improve Claude's performance on complex tasks. Each mode targets a different thinking style.

### Modes

| Mode | Purpose | Best For |
|------|---------|----------|
| **megamind-deep** | Systematic analysis — surface assumptions, consider alternatives, assess risks | Architecture decisions, debugging, scope clarification |
| **megamind-creative** | Structured creative chaos — pattern-mining, analogies, constraint mutation | Creative problem-solving, brainstorming, unconventional solutions |
| **megamind-adversarial** | Red-team — attack the obvious approach, find failure modes, stress-test | Security review, design review, finding weaknesses |
| **megamind-financial** | Multi-domain financial analysis — investment valuation (Thorleif Jackson methodology), DK/DE tax planning, mortgage, pension, insurance | Stock valuation, tax optimization, loan/mortgage analysis, retirement planning |

`megamind-deep` and `megamind-creative` are auto-selected during `setup.py init`. The adversarial and financial variants are opt-in.

The `megamind-financial` skill uses country-specific data files in `cli/claude/skills/megamind-financial/data/` (e.g., `dk-tax-2026.md`). See [cli/claude/skills/IMPROVEMENT-PROCESS.md](cli/claude/skills/IMPROVEMENT-PROCESS.md) for the annual DK tax data update procedure.

### Benchmarks — model × task performance

> **Full data, methodology, and caveats: [docs/BENCHMARKS.md](docs/BENCHMARKS.md).**

Skills are evaluated with a rubric-based judge (prose tasks) and with objective
test-pass scoring (agentic coding). Subjects run across the model matrix —
**gpt-5.5, gpt-5.4(-mini), claude-opus-4.7/4.6, claude-sonnet-4.6** — so you can
pick the right model *and* skill per task. Headlines:

**Which skill for which task** (rubric score, avg across models; each skill wins its own category):

| Task | best skill | skilled score | baseline |
|------|-----------|--------------|----------|
| Deep reasoning (migration, refactor, API design) | **megamind-deep** | 8.4 | 5.0 |
| Architecture under ambiguity | **megamind-deep** | 7.0 | 3.6 |
| Open-ended / creative | **megamind-creative** | 7.8 | 4.8 |
| Red-team / design review | **megamind-adversarial** | 7.1 | 5.4 |
| Vague requests ("make it faster") | **megamind-deep** (scope gate) | ~6.0 | ~0 |
| Financial (valuation, DK/DE tax) | **megamind-financial** | 7.5 | ~5 |

**Which model.** On **reasoning/financial prose**, Claude (opus-4.7, sonnet-4.6)
leads at baseline and skilled; the GPTs start lower but gain most from skills. On
**agentic coding** the ranking flips — gpt-5.5 ≈ 74% on a representative
SWE-bench Verified sample (our scaffold) and tops the harder DeepSWE benchmark,
where Claude trails. Pick by task: **Claude for judgment/analysis, gpt-5.5 for
large multi-file coding.**

**The skill principle.** Skills help **in inverse proportion to model strength** —
big lift on weaker models/baselines (scope +5–7 on lesser models; financial +2.3
on Sonnet), little-to-none on frontier models on coding (gpt-5.5 agentic net-0).
So: **always enable the megamind skills for reasoning/financial/scope** (clear
win, every model, ~free); for **agentic coding, rely on a strong model** —
reasoning skills are upside only on weaker ones.

The **scope gate** (added after benchmarking found vague prompts were the one
universal weakness) takes every model from cratering (~0, almost never passing)
to the rubric ceiling (~6, ~100% pass) — see [docs/BENCHMARKS.md §3](docs/BENCHMARKS.md).

### Challenge Format

Challenges are YAML files in `tests/challenges/`:

```yaml
id: arch-001
name: "Architecture Decision Under Ambiguity"
category: reasoning_depth
skill: megamind-deep
prompt: |
  Add real-time notifications to our Django app...
rubric:
  required_elements:
    identifies_assumptions: "Lists assumptions about scale, notification types"
    considers_alternatives: "Mentions at least 2 architectural approaches"
  anti_patterns:
    jumps_to_code: "Immediately writes implementation code"
  passing_score: 6
```

### Running the Benchmark

Subject and judge each run via the **claude**, **copilot**, **codex** (`codex exec`)
or **agy** (Antigravity, `agy -p`) CLI (authenticated, in PATH). Defaults to
claude; use the backend flags to pick the model matrix (`CODEX_EFFORT` /
`AGY_EFFORT` set the reasoning effort for those two). See [docs/BENCHMARKS.md](docs/BENCHMARKS.md) for full methodology.

```bash
# Default (claude CLI, all skills)
python3 tools/run_benchmark.py --runs 3 --save results/out.json

# Specific skill (baseline auto-included for comparison)
python3 tools/run_benchmark.py --skill megamind-deep --runs 3

# Multi-model via Copilot, judged by latest opus (claude)
python3 tools/run_benchmark.py --challenges scope-001 scope-002 --skill megamind-deep --runs 3 \
  --subject-backend copilot --subject-model gpt-5.5 \
  --judge-backend claude --judge-model opus

# Dual-judge (gpt-5.5 + latest opus) — flags disagreements for human review
... --judge2-backend copilot --judge2-model gpt-5.5 --judge-disagree-threshold 2

# Max reasoning effort (Copilot subjects)
COPILOT_EFFORT=max python3 tools/run_benchmark.py ...
```

**Agentic coding** (objective, test-pass scored — no judge):

```bash
# SWE-bench Verified via Copilot + Docker eval
python3 tools/run_swebench_agentic.py --model gpt-5.5 --instances pallets__flask-5014

# DeepSWE via Copilot (no API keys) — setup in tools/deepswe/README.md
```

## Review Process

A tiered review-orchestration skill that turns scattered reviewers into a disciplined workflow. Default-on in `setup.py init`; activates on `/review-process` or whenever a change/decision/PR is about to be reviewed.

> **Rollout note for existing projects.** `review-process` is in the `always_on` set, so it auto-appears on the next `/update-foundry` even if it's missing from a stale manifest. The skill is dormant until invoked — adding the files costs ~30 KB on disk and zero runtime overhead until you use `/review-process`. To remove it, delete `.claude/skills/review-process/` and `.claude/commands/review-process.md` after the update; foundry will re-add them on the run after that unless you also remove it from `always_on` in `tools/setup.py`. If this default-on behavior is unwanted, file an issue and we'll move it to a normal opt-in toggle.

### What it adds

- **Risk tiers T0–T4** — mechanical → normal → integrated → high-risk → release/post-incident
- **Review modes** — `AUDIT_ONLY`, `FIX_AUTHORIZED`, `FIX_AND_COMMIT_AUTHORIZED`
- **Model strategies** — `SINGLE_FAST`, `DIVERSE_STANDARD`, `PREMIUM_TARGETED`, `MIXED_PREMIUM`, `USER_SPECIFIED`
- **Reviewer routing** — triggers map to existing foundry reviewers (`megamind-*` skills + `code-reviewer-*`, `security-reviewer-*`, `tdd-guide-*`, `architect-*`, `refactor-cleaner-*`, `build-error-resolver-*` agents)
- **Finding ledger** — every finding gets severity, confidence, evidence strength, disposition, and prevention action
- **Reviewer compaction** — at most one reviewer per concern; adversarial covers cross-concern interactions
- **Persistent review state** — recurring findings, converted checks, deferrals, and accepted risks live in the project at `docs/review-state/log.md` (seeded on first use from the skill's templates)

### Layered sub-files (additive)

| File | Applies to |
|------|-----------|
| `SKILL.md` | Canonical entry — shared tiers/modes/routing/ledger/state |
| `general.md` | Non-software decisions, plans, documents, policies |
| `software.md` | Any-language code change (smells, omissions, architecture, tests) |
| `python.md` | Python code, packaging, scripts, libraries |
| `python-non-gui.md` | Python CLI/service/worker/library |
| `python-gui.md` | PySide6/PyQt/Qt desktop GUI (references `gui-threading` + `python-qt-gui` skills) |

Always start with the general process and add every more-specific sub-file whose trigger applies.

### Relationship to other foundry artifacts

- Complements `pr-review-toolkit` (which reviews already-created PRs) — this skill governs pre-commit / pre-PR review.
- Complements the `code-review` plugin (single-shot review) — this skill is a tiered governance process.
- Routes work to skills/agents foundry already ships; if a referenced reviewer isn't installed, the review header records it as unavailable.

## Copilot CLI

Foundry no longer ships a VS Code extension or MCP bridge for Copilot. With the
GitHub Copilot CLI installed locally, reaching non-Claude models is trivial — a
single `copilot -p` invocation — so the bridge, its 7 `/copilot-*` skills, and
the per-workspace runtime gymnastics were retired in favour of a thin reference
skill.

The `copilot-cli` skill (auto-installed, like `review-process`) documents the
one canonical call:

```bash
copilot -p "<prompt>" --model <model> --allow-all-tools -s
```

- **Prerequisite:** the `copilot` GitHub Copilot CLI on `PATH`, authenticated
  (`copilot` once interactively to sign in). Verify with `copilot --version`.
- **Token cost:** spends your GitHub Copilot subscription, not Anthropic tokens.
- **Primary consumer:** `review-process` references it to run a second,
  cross-model reviewer (e.g. `gpt-5.4`) under the `DIVERSE_STANDARD` strategy.
  If `copilot` is not installed, review-process falls back to a second Claude
  run automatically — the CLI is an enhancement, never a hard dependency.

See `skills/copilot-cli/SKILL.md` for the full invocation contract and model
notes. There is no installer, no MCP server, and nothing to enable per
workspace — if `copilot` runs in your shell, it works.

Two sibling reference skills, also auto-installed, do the same for the other
local CLIs: `codex-cli` (`codex exec … -s read-only -o <file> </dev/null` for
OpenAI models without a Copilot subscription) and `agy-cli`
(`agy -p … --output-format json` for Gemini models). `review-process` probes
for all three and routes its cross-vendor reviewer through whichever is
installed.

## Delegation

The `delegate` skill lets a session in one coding-agent CLI hand a task to
another — Claude Code → Codex, Codex → Antigravity, Copilot → Claude Code, any
direction — as a managed job. It deploys to every target CLI
(`.claude/skills/` and `.agents/skills/`), and every run goes through one
stdlib-only runner, `scripts/delegate.py`:

```bash
python3 .claude/skills/delegate/scripts/delegate.py start --to codex --job fix-auth --task "..."
python3 .claude/skills/delegate/scripts/delegate.py wait fix-auth    # JSON result
python3 .claude/skills/delegate/scripts/delegate.py diff fix-auth    # review
python3 .claude/skills/delegate/scripts/delegate.py merge fix-auth   # after approval
```

(`.agents/skills/delegate/...` from Copilot CLI, Codex and Antigravity.)

- **Isolation:** a write job runs in its own git worktree
  (`../<repo>-delegate-<job>`, branch `delegate/<job>`); `--mode read-only`
  runs in place under the target's read-only settings. Nothing reaches your
  branch until `merge`.
- **Policy:** `.delegate/policy.json` (committable) sets which targets are
  allowed, whether writes are, delegation depth (default: a delegate may not
  delegate again), concurrency, timeouts and per-target models.
- **Accountability:** a normalized JSON result for every target (status,
  summary, files changed, commits, usage, warnings). Job records and an
  event log in `.git/delegate/`, shared by all worktrees. Warnings when a
  read-only run writes, a delegate switches branch, or any ref moves.
- **Supervision:** every run has a detached supervisor that owns the
  target's process group, enforces the timeout, honours `cancel` (SIGTERM,
  then SIGKILL) and records the result, so a host whose shell tool times out
  loses nothing.
- **Clean hand-off:** the child gets depth and chain markers, none of the
  parent session's variables (some are credentials), and only its own CLI's
  credentials.
- **Follow-ups:** `run --job <job> --resume` continues in the same worktree
  and the target's previous conversation.

Run delegate commands outside the host CLI's own sandbox; the runner refuses
inside Codex's. `delegate.py doctor` shows which CLIs are installed, the
active policy, and caveats such as a Codex sandbox that can't start. Details:
[`cli/claude/skills/delegate/scripts/README.md`](cli/claude/skills/delegate/scripts/README.md).

## Project Management

Named project contexts let you juggle multiple parallel initiatives without losing state between sessions. Each project lives in `.claude/prjs/<name>.md` — a simple markdown file with YAML frontmatter tracking goal, status, decisions, key files, and the last Claude session ID.

### Workflow

```
/prj-new bank-refactor          # Create project, open file for editing
/prj-pause bank-refactor        # Save state (records current session_id)
/prj-list                       # See all projects, their status, resume commands
/prj-resume bank-refactor       # Reload context — suggests `claude --resume <id>`
/prj-done bank-refactor         # Mark complete
/prj-delete bank-refactor       # Remove
```

### Project file

A project file looks like:

```markdown
---
name: bank-refactor
status: active            # active | paused | done
updated: 2026-04-04T14:22
session_id: abc123...     # Set on /prj-pause
---

## Goal
Migrate the legacy /api/accounts endpoints to the new service.

## Status
- [x] Inventoried existing callers
- [ ] Draft compatibility shim
- [ ] Migration plan

## Decisions
- Use adapter pattern rather than parallel rewrite

## Key Files
- src/api/accounts.py
- tests/test_accounts.py

## Resume
What to pick up next session...
```

### How session tracking works

On `/prj-pause`, the script records the current Claude session ID into the project file via the shared `skills/_lib/session-id.sh` library (it reads `.claude/projects/<encoded-cwd>/` to find the active session JSONL). On `/prj-resume`, the skill reads it back and suggests `claude --resume <session_id>` so you can continue the exact same conversation — or start a fresh session with full project context loaded.

### When to use this vs `/snapshot`

| Feature | Use `/prj-*` | Use `/snapshot` |
|---------|--------------|-----------------|
| Long-lived named initiative | ✓ | |
| Running multiple projects in parallel | ✓ | |
| Point-in-time session capture | | ✓ |
| Stateful session resumption by ID | ✓ | |

All `prj-*` skills are auto-installed by `setup.py`.

## Credits

Inspired by [everything-claude-code](https://github.com/affaan-m/everything-claude-code) by Affaan M.

## License

MIT
