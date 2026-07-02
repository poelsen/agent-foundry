# Claude Code Skills

Skills are reusable knowledge modules that provide domain-specific patterns, best practices, and implementation guidance.

> **Skill groups in `setup.py init`:** Megamind Reasoning (4 skills) and Project Management (6 skills) are toggled as groups, not individually. See the top-level [README — Skill Selection](../README.md#skill-selection-groups-hidden-skills-gating) section for details.

## Available Skills

### GUI Development

| Skill | Purpose | When to Use |
|-------|---------|-------------|
| [gui-threading](gui-threading/) | Framework-agnostic GUI threading | Any multithreaded GUI |
| [python-qt-gui](python-qt-gui/) | Python/Qt specific patterns | PySide6/PyQt6 apps |

**Relationship:** `python-qt-gui` extends `gui-threading`. Read the base skill first.

### Megamind Reasoning

| Skill | Purpose | When to Use |
|-------|---------|-------------|
| [megamind-deep](megamind-deep/) | Systematic analysis, multiple approaches, risk assessment | Complex or ambiguous problems |
| [megamind-creative](megamind-creative/) | Structured creative chaos — pattern-mining, mutation, analogies, compression | Creative tasks, hard problems, when conventional approaches fail |
| [megamind-adversarial](megamind-adversarial/) | Red-team — attack the obvious approach, stress-test | When you need to find weaknesses |
| [megamind-financial](megamind-financial/) | Multi-domain financial analysis — investment valuation (Thorleif Jackson methodology), DK/DE tax planning, mortgage, pension, insurance | Stock valuation, tax optimization, loan analysis, retirement planning |

**Auto-selected:** `megamind-deep`, `megamind-creative`. The adversarial and financial variants are opt-in.

The `megamind-financial` skill uses country-specific data files in `data/` (e.g., `dk-tax-2026.md`). See [IMPROVEMENT-PROCESS.md](IMPROVEMENT-PROCESS.md) for the annual DK tax data update procedure.

#### Benchmark Results (Opus 4.6, original 30-challenge suite, 5 runs each)

The results below are from the original 30-challenge suite — the 6 categories in the per-category table, 5 challenges each (financial not yet included). The suite has since grown to 109 challenges (current counts under Challenge Categories); for current multi-model results see [docs/BENCHMARKS.md](../../../docs/BENCHMARKS.md). Each challenge has a rubric with required elements and anti-patterns, scored by a Claude-as-judge pipeline.

**Overall Performance:**

| Mode | Avg Score | Pass Rate | Variance | Delta vs Baseline |
|---|---|---|---|---|
| Baseline (no skill) | 5.0 | 62% | high | — |
| megamind-deep | 6.7 | 82% | low | +1.7 |
| megamind-creative | 6.4 | 78% | low | +1.4 |
| megamind-adversarial | 6.5 | 80% | low | +1.5 |

**Per-Category Breakdown (best mode bolded):**

| Category | Challenges | Baseline | Deep | Creative | Adversarial | Winner |
|---|---|---|---|---|---|---|
| adversarial | 5 | 6.5 | 7.5 | 7.6 | **7.7** | adversarial |
| arch | 5 | 6.2 | **7.3** | 6.5 | 6.6 | deep |
| creative | 5 | 4.7 | 7.0 | **8.0** | 7.0 | creative |
| cross | 5 | 9.0 | **9.5** | 9.0 | 9.3 | deep |
| deep | 5 | 5.6 | **7.0** | 6.6 | 6.9 | deep |
| scope | 5 | 1.4 | 2.4 | 1.8 | **2.6** | adversarial |

**Key findings:**
- Each skill dominates its target category (creative on creative tasks, adversarial on adversarial tasks, deep on arch/deep/cross)
- All skills dramatically reduce variance vs baseline — more consistent results
- Scope challenges expose a fundamental weakness: Opus jumps to solutions instead of asking clarifying questions for vague prompts, even with skills active
- Cross-cutting challenges (stakeholder conflicts, incident response) score highest across all modes

**Running the benchmark** (requires `claude` CLI authenticated and in PATH):

```bash
# Full run (109 challenges x 5 modes x 5 runs = 2725 combos)
python3 tools/run_benchmark.py --workers 24 --runs 5 --save results/output.json

# Single challenge smoke test
python3 tools/run_benchmark.py --workers 1 --runs 1 --challenges arch-001

# Specific skill only (always includes baseline)
python3 tools/run_benchmark.py --skill megamind-deep --runs 3

# Compare against saved baseline
python3 tools/run_benchmark.py --runs 5 --save results/new.json --compare results/old.json
```

#### Challenge Categories

Challenges are YAML files in `tests/challenges/`. Each defines a prompt, required rubric elements, anti-patterns, and a passing score. Counts are the current suite (109 total); the Elements / Anti-patterns / Passing columns show the original rubric shape, which varies for newer challenges.

| Category | Count | Elements | Anti-patterns | Passing | Tests |
|---|---|---|---|---|---|
| adversarial | 12 | 8 | 3 | 6 | Red-teaming designs (caching, auth, feature flags, migrations, pipelines) |
| arch | 5 | 8 | 3 | 6 | Architecture decisions under ambiguity (DR strategy, build vs buy, event-driven, API gateway) |
| creative | 12 | 8 | 3 | 6 | Creative problem-solving (rate limiting, CLI redesign, onboarding, alert fatigue, code review) |
| cross | 5 | 10 | 3 | 7 | Cross-cutting concerns (stakeholder conflicts, incidents, security breaches, tech debt) |
| deep | 12 | 8 | 3 | 6 | Deep reasoning (DB migration, refactoring, API design, testing strategy, zero-downtime deploys) |
| financial | 58 | 8 | 3 | 6 | Financial analysis (valuation, Thorleif scoring, data quality, cyclicals, REITs, portfolio construction) |
| scope | 5 | 6 | 2 | 4 | Scope clarification for vague requests ("make it faster", "fix search", "improve UX") |

### Validation Methodology

Skill benchmark scores are produced by LLM-as-judge evaluation (Claude scoring Claude's output against YAML rubrics). These scores measure rubric compliance and structural quality, **not human-expert-validated correctness**. The scores are useful for:
- Regression testing (did a skill change break something?)
- Comparative ranking (does the skill outperform baseline on its own domain?)
- Iterative improvement (which rubric elements does the skill miss?)

The scores should NOT be interpreted as:
- Professional-quality validation of financial, legal, or medical advice
- Correlation with domain expert judgment (this has not been measured)
- Proof that skill responses are "correct" in any absolute sense

Real-world validation comes from usage by software engineers who report that the skills produce qualitatively better analysis, more thorough risk identification, and more actionable recommendations than unguided prompts. This is anecdotal and experience-based, not statistically measured.

### Writing

| Skill | Purpose | When to Use |
|-------|---------|-------------|
| [writer](writer/) | Proactive drafting in the author's voice — blog posts, emails, letters, applications, complaints, data-driven pieces | Writing fresh text from scratch |
| [humanizer](humanizer/) | Reactive editor that strips AI-writing tells (29 pattern categories) and runs a "what makes this obviously AI?" audit | Editing or reviewing existing text |

**Relationship:** the pair is one pipeline. `writer` drafts human-first (intake → voice card → outline → draft), then invokes `Skill(humanizer)` once as its automatic self-audit; user revisions afterwards are unlimited. They are grouped as **Writing** in the setup menu (opt-in, not auto-selected) and must deploy together — `writer`'s hand-off fails without `humanizer` present.

`writer` keeps its core lean and loads sub-files on demand: an always-on craft core (`general-writing.md`), six genre files (blog, email, personal/formal letter, application, complaint), a verified exemplar canon (`exemplars.md` — techniques from Buffett, Marks, Damodaran, Levine, Feynman, Zinsser, Williams and others, with the quote-folklore stripped), and **ten selectable voice presets** under `voices/` (index: `voices.md`). The default preset is the `house-blend` (the author's documented voice elevated with a few borrowed moves); `jens-andersen` is the strict-imitation baseline; the other eight cover plain-authoritative, witty-explanatory, transparent-teacher, narrative-nonfiction, science-explainer, contrarian value-blogger, radical-brevity, and literary-clarity registers. Invoke naturally ("draft a complaint about X", "write this in the transparent-teacher voice") or via `/writer`.

### Specialized Domains

| Skill | Purpose | When to Use |
|-------|---------|-------------|
| [clickhouse-io](clickhouse-io/) | ClickHouse analytics patterns | Data engineering |

### Copilot CLI

| Skill | Purpose | When to Use |
|-------|---------|-------------|
| [copilot-cli](copilot-cli/) | Local GitHub Copilot CLI invocation contract | Running a non-Claude model (e.g. `gpt-5.4`) for cross-model review |

Reference skill, not a slash command. `review-process` consults it to run a
second cross-model reviewer via `copilot -p`. Requires the `copilot` CLI on
`PATH`; if absent, review-process falls back to a second Claude run. See the
top-level [README — Copilot CLI section](../README.md#copilot-cli).

### Project Management

Named project contexts let you work on multiple parallel initiatives without losing state. Each project lives in `.claude/prjs/<name>.md` with goals, status, decisions, and key files.

| Skill | Purpose | Command |
|-------|---------|---------|
| [prj-new](prj-new/) | Create a new named project | `/prj-new <name>` |
| [prj-list](prj-list/) | List all projects with status | `/prj-list` |
| [prj-pause](prj-pause/) | Save session state, mark paused | `/prj-pause <name>` |
| [prj-resume](prj-resume/) | Load project context, resume work | `/prj-resume <name>` |
| [prj-done](prj-done/) | Mark project complete | `/prj-done <name>` |
| [prj-delete](prj-delete/) | Delete a project file | `/prj-delete <name>` |

The script-based prj-* skills share [`_lib/session-id.sh`](_lib/session-id.sh) to detect the current Claude session and record it on pause, so `/prj-resume` can suggest `--resume <session_id>`.

**Auto-selected:** All prj-* skills are installed by default via `setup.py`.

## Skill Structure

Each skill directory contains:

```
skill-name/
├── SKILL.md    # Main skill content (required)
└── README.md   # Documentation (optional)
```

### SKILL.md Format

```markdown
---
name: skill-name
description: Brief description for skill discovery
extends: base-skill  # Optional: for extension skills
---

# Skill Title

Skill content with patterns, examples, checklists...
```

## How Skills Work

1. **Activation**: Skills are loaded based on context (project type, file patterns, explicit request)
2. **Content**: Provides patterns, code examples, checklists, anti-patterns
3. **Rules**: Skills often pair with rules files for non-negotiable constraints

## Skill vs Rule

| Aspect | Skill | Rule |
|--------|-------|------|
| Purpose | Guidance, patterns | Constraints, mandates |
| Tone | "Here's how to..." | "You MUST/MUST NOT..." |
| Flexibility | Multiple valid approaches | Non-negotiable |
| Location | `.claude/skills/` | `.claude/rules/` |

## Learned Skills

Patterns extracted from sessions via `/learn`. Organized by category:

```
skills/learned/
├── python/          # Python-specific patterns
├── debugging/       # Debugging techniques
└── <category>/      # Any category
    └── <pattern>.md
```

- **Shared** (`skills/learned/<cat>/`): Deployed to projects via `setup.py`, synced across machines
- **Project-local** (`<project>/.claude/skills/learned-local/<cat>/`): Project-specific, not managed by setup.py

Use `/recall` to list or search learned skills. Use `/learn` to extract new patterns.

Categories are selected during `setup.py init` — projects only get relevant categories.

## Creating New Skills

1. Create directory: `.claude/skills/my-skill/`
2. Create `SKILL.md` with YAML frontmatter
3. Add `README.md` for documentation
4. If it has non-negotiables, create matching rule in `.claude/rules/`

### Extension Skills

For framework-specific implementations:

```yaml
---
name: framework-specific-skill
extends: base-skill
---
```

Start content with: "This skill extends `base-skill`. Read that first."

## GUI Threading Skills

The `gui-threading` and `python-qt-gui` skills are based on:

- **MIT 6.005**: Thread safety strategies
- **KDAB**: Eight Rules of Multithreaded Qt
- **Facebook Flux**: Unidirectional data flow
- **Redux**: Immutable state management
- **Martin Fowler**: Event sourcing patterns

Key patterns:
- UI thread protection (no backend work)
- One-way data flow (Backend → Controller → Model → View)
- Worker job pattern (signals, cancellation)
- Immutable snapshots (frozen dataclass + tuple)
- Debounced event-driven refresh
- Multipane dock layouts

See [gui-threading/README.md](gui-threading/README.md) for details.
