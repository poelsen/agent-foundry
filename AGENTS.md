# agent-foundry

<!-- agent-foundry -->
## Coding Standards (agent-foundry)

These standards are managed by agent-foundry and apply to any CLI that reads `AGENTS.md`. Setup rewrites this block on every update — keep project-specific instructions outside it.

### Environment

```bash
uv sync --extra dev  # Setup
uv run pytest  # Tests
```

### Project Docs

- `codemaps/INDEX.md` — read before modifying unfamiliar modules; run the `update-codemaps` command after significant structural changes
- `docs/ARCHITECTURE.md` (design decisions) and `docs/DEVELOPMENT.md` (setup and workflow), if present

<!-- rule: coding-style.md -->
### Coding Style (Core)

#### Change Philosophy

- Minimal diffs; avoid unrelated refactors
- Correctness → Clarity → Performance
- Don't optimize without measurement
- **KISS**, **YAGNI**, **DRY**

#### Functions

- Small and single-purpose (<50 lines)
- If "and" in the name, it's doing too much
- Pure where possible; isolate side effects

#### Data & State

- Prefer immutable data structures
- Avoid shared mutable state
- Strong types at boundaries

#### Error Handling

- Fail fast with meaningful messages
- Handle at appropriate boundaries
- Log with context; don't swallow silently

#### Naming & Comments

- Self-documenting names reduce comment need
- "What/why" comments OK; "how" comments are smell
- Document decisions for non-obvious tradeoffs

#### Core Checklist

Before marking work complete:
- [ ] Minimal diff (no unrelated changes)
- [ ] Functions small and focused
- [ ] No deep nesting (>4 levels)
- [ ] Proper error handling
- [ ] No debug statements in production
- [ ] No hardcoded secrets

See project-specific styles in rule-library/style/.

<!-- rule: git-workflow.md -->
### Git Workflow

#### Branch Strategy

Feature Branch Workflow: short-lived branches, rebase only (no merge commits), squash before merge.

**Protected:** `master`, `release/*` — never push directly, require PR + review + CI pass.

#### Branch Naming

```
feature/<initials>_<issue>_<desc>   bugfix/<initials>_<desc>
release/<major>_<minor>_<patch>     devel/<initials>_<desc>
```

Delete feature/bugfix branches after merge.

#### Commit Format

```
[ISSUE-ID] <type>: <subject>

<body - wrap at 72 chars>

AI: <assisting model, e.g. Claude Opus 5.5 or gpt-6.1-sol>
```

- Subject: 50 chars target, 70 max, imperative mood
- Types: feat, fix, refactor, docs, test, chore, perf, ci
- ISSUE-ID optional. See `github.md` for `Closes #N` linking.

#### Pull Requests

1. Analyze full commit history with `git diff [base]...HEAD`
2. Draft comprehensive summary
3. Include test plan

#### Release & Hotfix

Release: tag on master → hotfix needed: branch from tag → bugfix branch → fix → new tag → cherry-pick to master.

<!-- rule: security.md -->
### Security Guidelines

#### Mandatory Checks (before ANY commit)

- [ ] No hardcoded secrets (API keys, passwords, tokens)
- [ ] All user inputs validated
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (sanitized HTML)
- [ ] CSRF protection enabled
- [ ] Authentication/authorization verified
- [ ] Rate limiting on endpoints
- [ ] Error messages don't leak sensitive data

#### Secret Management

Use env vars, never hardcode secrets.

#### Security Response

If security issue found:
1. STOP immediately
2. Use **security-reviewer** agent
3. Fix CRITICAL issues before continuing
4. Rotate any exposed secrets

<!-- rule: testing.md -->
### Testing Requirements

#### Minimum Test Coverage: 80%

Test Types (ALL required):
1. **Unit Tests** - Individual functions, utilities, components
2. **Integration Tests** - API endpoints, database operations
3. **E2E Tests** - Critical user flows (Playwright)

#### Test-Driven Development

MANDATORY workflow:
1. Write test first (RED)
2. Run test - it should FAIL
3. Write minimal implementation (GREEN)
4. Run test - it should PASS
5. Refactor (IMPROVE)
6. Verify coverage (80%+)

#### Troubleshooting Test Failures

1. Use **tdd-guide** agent
2. Check test isolation
3. Verify mocks are correct
4. Fix implementation, not tests (unless tests are wrong)

#### Agent Support

- **tdd-guide** - Use PROACTIVELY for new features, enforces write-tests-first
- **e2e-test-typescript** - Browser E2E with Playwright (TS/JS)
- **e2e-test-python-web** - Browser E2E with Playwright (Python)
- **e2e-test-python-qt** - Desktop GUI E2E with pytest-qt (PySide6/PyQt)

<!-- rule: architecture.md -->
### Architecture Principles

#### Project Discovery

When implementing new functionality:
1. Search for battle-tested skeleton projects
2. Use parallel agents to evaluate options:
   - Security assessment
   - Extensibility analysis
   - Relevance scoring
   - Implementation planning
3. Clone best match as foundation
4. Iterate within proven structure

#### Design Principles

- Composition over inheritance
- Single responsibility per module
- Explicit dependencies (no hidden globals)
- Design for testability
- Minimize coupling between components

#### Module Boundaries

- Clear public API per module
- Dependencies flow inward (core has no external deps)
- Side effects at edges, pure logic in core

#### File Organization

- Many small files > few large files
- 200-400 lines typical, 800 max
- Organize by feature/domain, not by type
- Colocate related files (component + test + styles)
- Keep module boundaries visible in directory structure

See project-specific architecture in rule-library/arch/.

<!-- rule: codemaps.md -->
### Codemap System

#### Reading Codemaps

Before modifying code in an unfamiliar module:
1. Read codemaps/INDEX.md for project overview
2. Read the specific module codemap for context

Do NOT read all codemaps upfront. Read only what you need.

#### Updating Codemaps

Run /update-codemaps when:
- User requests it
- You've made structural changes (new modules, changed public APIs, new dependencies)

The command checks staleness automatically — only stale codemaps regenerate.

#### AGENTS.md Pattern

The agent-foundry block in AGENTS.md already points to codemaps/INDEX.md —
don't repeat it. A project without that block should include:

```
## Architecture
Read codemaps/INDEX.md before making changes to unfamiliar modules.
Run /update-codemaps after significant structural changes.
```

<!-- rule: python.md -->
### Language: Python

#### Tooling

- **Package manager**: `uv` | **Config**: `pyproject.toml` | **Build**: `hatchling`
- **Virtual env**: `.venv/` | **Lock**: `uv.lock` (commit it)

```bash
uv sync --extra dev                   # Setup (uses uv.lock)
uv run pytest                         # Test
uv run ruff check src tests           # Lint
uv run ruff format src tests          # Format
```

#### pyproject.toml Essentials

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "myproject"
version = "0.1.0"
requires-python = ">=3.11"

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov>=4", "ruff>=0.8"]

[tool.ruff]
target-version = "py311"
line-length = 100
select = ["E", "W", "F", "I", "B", "C4", "UP", "SIM", "PTH", "RUF"]
```

#### Style

PEP 8, type hints on functions, docstrings for public APIs, f-strings.

#### Code Quality

- [ ] Specific exceptions (no bare `except:`)
- [ ] Context managers for resources
- [ ] `pathlib` over `os.path`
- [ ] No mutable default arguments
- [ ] Don't mutate caller's data — return new objects

#### Error Handling

```python
except SpecificError as e:
    logger.error(f"Operation failed: {e}")
    raise UserFacingError("message") from e
```

#### Testing

pytest + fixtures + `parametrize`. Coverage target: 80%+.

<!-- rule: github.md -->
### GitHub Platform Rules

#### Commit Linking

GitHub auto-closes issues from commit **body** keywords only:

```
feat: Add retry logic

Closes #42
```

- `Closes #N`, `Fixes #N`, `Resolves #N` in commit body → auto-closes issue on merge
- `(#N)` in subject line → creates link only, does NOT close

#### Issues

- No GitHub Projects boards — issues live in the repo only
- Use `--json` with `gh issue view` / `gh pr view` (plain output errors on Projects classic)

<!-- rule: enterprise.md -->
### Security: Enterprise/Production

Extends `security.md` with strict requirements for production systems.

#### Additional Checks (BLOCK commit if violated)

- [ ] Secret manager for credentials (not env vars)
- [ ] CSP headers + output encoding for XSS
- [ ] Auth on ALL endpoints (explicit public allowlist)
- [ ] Authorization checks (RBAC/ABAC)
- [ ] Dependencies scanned for CVEs
- [ ] Secrets scanned in CI (gitleaks/git-secrets)

#### Data Protection

- Encrypt at rest and in transit (TLS 1.3)
- PII handling compliant with GDPR/privacy reqs
- Audit logging for sensitive operations
- Data retention policies enforced

#### Incident Response

Same as security.md, plus:
5. Review entire codebase for similar issues
6. Document in security log

<!-- rule: library.md -->
### Template: Libraries & Packages

#### API Design

- Minimal public surface area
- Consistent naming conventions
- Strong types over stringly-typed
- Make invalid states unrepresentable

#### Compatibility

- Semantic versioning
- Deprecate before removing
- Document breaking changes
- Minimal dependencies

#### Documentation

- README with quick start
- Docstrings on public APIs
- Examples that compile/run
- Changelog maintained

#### Checklist

- [ ] Public API is minimal
- [ ] Breaking changes documented
- [ ] Examples in docs work
- [ ] No unnecessary dependencies

<!-- rule: scripts.md -->
### Template: Scripts & CLI

#### Simplicity

- Optimize for readability, not abstraction
- Inline is fine; don't over-engineer
- Comments for "why", not "what"

#### Ergonomics

- Sensible defaults, explicit overrides
- Helpful --help output
- Exit codes: 0 success, non-zero failure
- Progress indicators for long operations

#### Safety

- Dry-run mode for destructive operations
- Confirm before irreversible actions
- Validate inputs early

#### Checklist

- [ ] Works with no arguments (or shows help)
- [ ] Clear error messages
- [ ] Non-zero exit on failure
- [ ] No hardcoded paths

<!-- /agent-foundry -->
