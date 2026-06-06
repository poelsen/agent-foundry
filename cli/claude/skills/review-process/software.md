# Software Review Process

Use this process for any software change, regardless of language or framework.
It extends [SKILL.md](SKILL.md) and the [general review process](general.md)
with code, test, architecture, regression, and automation checks.

## Goal

The review should determine whether the change is correct, maintainable,
tested, architecture-safe, and hardened against future regression.

## Software risk triggers

Escalate the risk tier when a change touches:

- public APIs or compatibility boundaries
- persistence, migrations, caches, or stored identifiers
- concurrency, cancellation, lifecycle, or async behavior
- security, user input, secrets, filesystem paths, network, or serialization
- test harnesses or shared fakes/fixtures
- dependency graph, packaging, build, release, or deployment
- cross-module architecture or long-lived dual APIs

## Software reviewer routing

| Trigger | Executed reviewer/frame | Rule set to apply |
|---------|-------------------------|-------------------|
| Any meaningful code change | `megamind-deep` or `megamind-adversarial` by tier | Software checklist |
| Non-trivial scope, sequencing, rollback, compatibility | Pragmatic frame | Shared completion and authority policy |
| Architecture or public API boundary | `architect-*` agent for the stack | Architecture checklist |
| Security, input, persistence, path, secret, or sharing risk | `security-reviewer-*` agent | Security checklist for the stack |
| Feature, bug fix, or regression-sensitive change | `tdd-guide-*` agent | Test checklist |
| Cleanup, migration completeness, dead code, duplicate logic | `refactor-cleaner-*` agent | Code-smell and migration checklist |
| Build, lint, type, test, dependency, or packaging failure | `build-error-resolver-*` agent | Existing tool output |
| New decomposition or T4 review | `megamind-creative` | Alternate decomposition review |

Substitute the language suffix as installed: `-python`, `-typescript`,
`-python-web`, `-python-qt`. If the agent for the stack is not installed,
record the gap in the review header.

## Review flow

1. Declare review mode, risk tier, budget, and triggers.
2. Select reviewers using shared routing plus software triggers.
3. Pre-review T3/T4 plans for architecture, rollback, migration, and tests.
4. Post-review changed files plus integration contracts.
5. Triage findings with the shared ledger.
6. Apply fixes only when the review mode authorizes edits.
7. Validate with existing project checks.
8. Promote recurring findings into review-state checks.

## Code-smell checklist

Smells are prompts, not automatic severity. A finding needs concrete impact.

- [ ] Long parameter lists (>5 args without a data object)
- [ ] Functions >50 lines doing more than one thing
- [ ] Nested conditionals >3 levels deep
- [ ] Hidden globals or module-level mutable state
- [ ] Dual-API coexistence beyond one explicit deprecation horizon
- [ ] Monkey-patched attributes instead of constructor injection
- [ ] Defensive reads for fields the same class should initialize
- [ ] Dead production code
- [ ] Dead production state: fields written but never read, or read but never
      written
- [ ] Polymorphic event/signal payloads carrying incompatible shapes
- [ ] Silent contract violations: documentation claims one behavior, code does
      another
- [ ] String-typed identifiers that should be typed values
- [ ] Boolean function arguments where an enum or explicit keyword is clearer
- [ ] Magic numbers without named constants
- [ ] Swallowed errors without logging or propagation
- [ ] Over-broad exception handling without narrow boundary intent

## Test-smell checklist

- [ ] Tests mock the integration point under test
- [ ] Tests assert behavior the test itself set up
- [ ] Tests depend on global state from prior tests
- [ ] Tests use sleeps/timers instead of deterministic synchronization
- [ ] Tests skip to hide flakiness rather than controlling it
- [ ] Success path covered without failure/error partitions
- [ ] Test doubles do not honor production signatures or invariants
- [ ] Regression test verifies the root contract, not only the symptom

## Architecture checklist

- [ ] Module dependency graph remains acyclic where intended
- [ ] Dependencies point in the correct direction
- [ ] Mutable state has one clear owner
- [ ] Cross-layer leakage is avoided
- [ ] Public APIs do not accept both typed values and legacy string forms
      without a removal horizon
- [ ] Optional values are handled at the boundary, not silently passed inward
- [ ] Identifier stability is based on stable inputs, not display names or
      incidental ordering
- [ ] Compatibility bridges have explicit deprecation and removal points

## Omission checklist

Review what should have changed but did not.

- [ ] New public API has tests and documentation or an explicit reason not to.
- [ ] New dependency has dependency review, sync/lock update, and security
      consideration.
- [ ] New persisted field has migration/backward-compatibility coverage.
- [ ] New user-visible behavior has regression coverage.
- [ ] New configuration has defaults, validation, and failure-mode coverage.
- [ ] Removed code has callers, docs, and tests migrated.
- [ ] New background/lifecycle behavior has shutdown/cancellation coverage.

## Validation guidance

Run only checks that already exist. Prefer the narrowest useful validation
first, then broaden based on risk:

1. targeted tests for the changed behavior;
2. relevant module/package tests;
3. full suite for T2+ or risky changes;
4. existing lint/type/build checks when code style, types, packaging, or
   shared APIs changed.

## Automation feedback loop

Recurring software findings should become one of:

- unit/integration/regression test;
- lint/static-analysis rule;
- fixture or fake that makes the safer path easier;
- code template or example;
- review checklist item;
- architecture/codemap documentation.

Every conversion must create or update a review-state entry.

## Commit message template

```text
feat(<scope>): <title>

<short description>

Reviewer-driven hardening pass:
- Mode: <mode>
- Risk tier: T<N>
- Reviewers: <actual reviewers and evidence>
- Key risks reviewed: <threading, persistence, tests, security, etc.>

Findings resolved:
- CRITICAL: <count fixed/deferred/rejected>
- HIGH: <count fixed/deferred/rejected>
- MEDIUM: <count fixed/deferred/rejected>
- LOW: <count fixed/deferred/rejected>

Automation/process improvements:
- <tests, checks, docs, templates>

Tests:
- <commands and result summary>
```
