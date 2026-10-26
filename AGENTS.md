# agent-foundry

<!-- agent-foundry -->
## Coding Standards (agent-foundry)

Managed by agent-foundry and rewritten on every update; keep project-specific instructions outside this block.

### Environment

```bash
uv sync --extra dev  # Setup
uv run pytest  # Tests
```

### Project Docs

- `codemaps/INDEX.md`, `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md` — read the ones that exist before working in an unfamiliar area

<!-- rule: coding-style.md -->
### Coding Style (Core)

#### Change Philosophy

- Minimal diffs; avoid unrelated refactors
- Correctness → Clarity → Performance
- Don't optimize without measurement
- **KISS**, **YAGNI**, **DRY**
- No debug leftovers (prints, commented-out code)

#### Working Method

- Reproduce a bug before fixing it
- Read the code you're changing, and its callers, before editing
- Smallest change that fixes the cause, not the symptom
- Verify by running it, and say what you ran
- State a routine assumption and continue; ask when different readings lead to materially different work

#### Functions

- Small and single-purpose (<50 lines), nesting no deeper than 4 levels
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

<!-- rule: git-workflow.md -->
### Git Workflow

#### Branch Strategy

Feature Branch Workflow: short-lived branches, rebase only (no merge commits), squash before merge.

**Protected:** `master`, `release/*` — never push directly; changes arrive by reviewed PR, with CI green where the repo has CI.

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
```

- Subject: 50 chars target, 70 max, imperative mood
- No AI attribution: no `AI:`, `Co-Authored-By:` or "Generated with" lines for a model or tool
- Types: feat, fix, refactor, docs, test, chore, perf, ci
- ISSUE-ID optional. See `github.md` for `Closes #N` linking.

#### Pull Requests

Summary from the full diff against the base branch, plus what was run to verify it. No AI attribution footer or session links.

<!-- rule: security.md -->
### Security Guidelines

#### Checks before a commit

Where the item applies to the code being changed:

- [ ] No hardcoded secrets (API keys, passwords, tokens)
- [ ] External input validated at the boundary (arguments, files, network, env)
- [ ] No string-built queries or shell commands from input (parameterize, pass argv lists)
- [ ] Error messages and logs don't leak secrets or private data

Web-facing code also needs the checks in the REST API template (auth on every endpoint, XSS and CSRF protection, rate limiting).

#### Secret Management

Use env vars, never hardcode secrets.

#### Never on your own initiative

Ask first, even when it would unblock you:

- Force-push, rewrite shared history, delete branches
- Delete or overwrite data; migrations or writes against anything shared
- Rotate or print credentials
- Stop or restart processes you didn't start

#### Security Response

If a security issue is found:
1. Stop and report it before continuing
2. Fix exploitable issues before other work; the **security-reviewer** agent helps judge severity
3. Rotate any exposed secrets

<!-- rule: testing.md -->
### Testing

#### What to run, and when

- While working, run the tests that cover what you changed, plus a quick sanity check if the project has one. Don't run the whole suite after every edit.
- Run the full suite before a merge when the change is wide (shared code, data models, build config) or when you can't tell what it touches. Say which run you did.
- Scheduled or CI runs catch regressions you didn't foresee; that is their job, not every edit's.
- Use the test command from the Environment section or the project's own notes. Don't invent a different one.

#### What to write

- A test for every behaviour you add or fix. Start with the test when it clarifies the behaviour; write it after when the shape of the code isn't clear yet.
- Test behaviour, not implementation. A test that mirrors the code it tests, or that only asserts the mock was called, proves nothing; leave it out.
- Keep each test independent of ordering and of other tests' state.
- Match the project's existing layout and fixtures.

#### Coverage

The project's own target applies. Where it has none, keep new code roughly as well covered as the code around it. Coverage is a signal, not a goal: don't write tests to move the number.

#### When a test fails

1. Read the failure before changing anything.
2. Fix the code, not the test, unless the test is wrong.
3. Check isolation: does it fail alone, and does it fail on a clean checkout?

#### Agents

- **tdd-guide** helps when the project runs test-first and the feature's behaviour is unclear.
- **e2e-test-typescript**, **e2e-test-python-web** (Playwright) and **e2e-test-python-qt** (pytest-qt) help for user-flow tests in a GUI or web app.

<!-- rule: architecture.md -->
### Architecture Principles

#### Starting a new project

When a project starts from nothing, look for a proven skeleton or template for its kind before writing the layout by hand. This doesn't apply to adding functionality to an existing project.

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

<!-- rule: codemaps.md -->
### Codemaps

Applies only to projects with a `codemaps/` directory; don't create one unasked.

- Before changing an unfamiliar module, read `codemaps/INDEX.md`, then that module's codemap. Not all of them.
- After a structural change (new module, changed public API, new dependency), run `/update-codemaps`; it regenerates only stale maps.

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

pytest + fixtures + `parametrize`.

<!-- rule: github.md -->
### GitHub Platform Rules

#### Commit Linking

GitHub auto-closes issues from commit **body** keywords only:

```
feat: Add retry logic

Closes #42
```

- `Closes #N`, `Fixes #N`, `Resolves #N` in commit body → auto-closes issue on merge
- `(#N)` in subject line → creates link only, does not close

#### Issues

- No GitHub Projects boards — issues live in the repo only
- Use `--json` with `gh issue view` / `gh pr view` (plain output errors on Projects classic)

<!-- rule: enterprise.md -->
### Security: Enterprise/Production

Extends `security.md` with strict requirements for production systems.

#### Additional Checks (fix before committing)

- [ ] Secret manager for credentials (not env vars)
- [ ] CSP headers + output encoding for XSS
- [ ] Auth on every endpoint (explicit public allowlist)
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
4. Review entire codebase for similar issues
5. Document in security log

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

<!-- /agent-foundry -->
