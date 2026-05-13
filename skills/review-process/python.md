# Python Review Process

Use this process for Python code, packaging, scripts, services, and libraries.
It extends [SKILL.md](SKILL.md), [general](general.md), and
[software](software.md). Add [Python non-GUI](python-non-gui.md) or
[Python GUI](python-gui.md) when their triggers apply.

## Python reviewer routing

| Trigger | Executed reviewer/agent | Rule set to apply |
|---------|-------------------------|-------------------|
| Python architecture, public API, module boundaries | `architect-python` | Python architecture rules |
| General Python quality after code changes | `code-reviewer-python` | Python quality checklist |
| User input, secrets, path traversal, deserialization, persistence, sharing | `security-reviewer-python` | Python security rules |
| New feature, bug fix, regression guard, test strategy | `tdd-guide-python` | Python test checklist |
| Dead code, duplicate logic, cleanup, migration completeness | `refactor-cleaner-python` | Migration/cleanup checks |
| Build, lint, type, pytest, dependency, or packaging failure | `build-error-resolver-python` | Existing tool output |

## Python quality checklist

- [ ] Public boundaries have clear types and avoid unnecessary `Any`.
- [ ] Dataclasses or small typed objects replace loose tuples/dicts for stable
      domain concepts.
- [ ] Mutable defaults are not used.
- [ ] Exceptions are narrow and include useful context.
- [ ] Broad `except Exception` is limited to boundary handling and logs or
      re-raises intentionally.
- [ ] Path handling is explicit and platform-safe.
- [ ] Serialization/deserialization handles untrusted input safely.
- [ ] Dependency imports are real runtime needs, not stale transitive pins.
- [ ] Optional dependencies are isolated behind clear feature boundaries.
- [ ] Scripts fail fast with clear messages and non-zero exit codes.

## Python test checklist

- [ ] Tests use real fakes for behavior that matters.
- [ ] Frozen dataclasses are constructed as real instances, not mocked.
- [ ] Pytest fixtures isolate filesystem, environment, global state, and
      caches.
- [ ] Error partitions are tested, not only success paths.
- [ ] Regression tests cover the contract that failed, not only the observed
      symptom.
- [ ] Parametrization is used for related cases instead of copy/paste tests.
- [ ] No test depends on execution order.

## Dependency and packaging checklist

- [ ] `pyproject.toml` direct dependencies are imports/features the project
      actually owns.
- [ ] Transitive dependencies are not pinned as direct dependencies unless
      there is a documented compatibility reason.
- [ ] Optional extras match actual optional features.
- [ ] Lock/sync state is updated with the repository's package manager.
- [ ] Tooling changes use existing tools instead of introducing new ones
      without need.
- [ ] Generated files and virtual environments are not committed.

## Python validation guidance

Run only checks that already exist. Prefer the narrowest useful validation
first, then broaden based on risk:

1. targeted pytest file or test selection for the changed behavior;
2. relevant package/module tests;
3. repository test suite for T2+ or risky changes;
4. existing lint/type/build checks when code style, types, packaging, or
   shared APIs changed.

Use the project's configured package manager (foundry default: `uv`). Run
Python via `uv run python` from the project root, or whichever invocation the
project's `CLAUDE.md` and `pyproject.toml` define.

## Python-specific severity adjustments

Escalate severity when:

- a type boundary is weakened to hide a bug;
- a broad exception swallows a real failure;
- a direct dependency is added without an owned import/feature;
- a test mocks away the behavior under review;
- a path or serialization change can behave differently across machines.

## Python output addendum

Python review findings should add this guard detail when applicable:

```text
Python guard: <pytest test, fixture/fake, type/lint check, dependency sync, or packaging validation>
```
