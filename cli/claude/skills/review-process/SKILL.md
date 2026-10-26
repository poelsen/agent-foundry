---
name: review-process
description: Tiered review process. Risk tiers T0-T3, review modes, reviewer routing to megamind/agent reviewers, finding ledger. Activate on /review-process or before risky commits, PRs or decisions.
model: opus
---

# Review Process

The entry point for tiered reviews: shared risk tiers, review modes, routing,
the finding ledger and closure. The sibling files add domain checks only.

## Load applicable sub-files before reviewing

Claude Code only auto-loads `SKILL.md`. The sub-files (`general.md`,
`software.md`, `python.md`, `python-non-gui.md`, `python-gui.md`) are loaded
only when you Read them. Before producing the review header:

1. Use the Process Selection table to determine which sub-files apply.
2. Read every applicable sub-file. Always include `general.md` plus every
   more-specific file whose trigger fires; they are additive.
3. Only then produce the review header and findings.

Skipping this drops the domain checklists and severity adjustments; the review
looks right but applies only the core.

## Process selection

| Work under review | Apply these processes |
|-------------------|-----------------------|
| Non-software decision, plan, document, policy, or operation | [General](general.md) |
| Software change in any language | General + [Software](software.md) |
| Python code, packaging, tests, scripts, services, or libraries | General + Software + [Python](python.md) |
| Python CLI, worker, service, library, or other non-GUI runtime | General + Software + Python + [Python non-GUI](python-non-gui.md) |
| PySide6/PyQt/Qt desktop GUI work | General + Software + Python + [Python GUI](python-gui.md) |

GUI and non-GUI are concern modules, not a tree: a change touching both gets
both, with reviewer selection compacted as described below.

## Intent

Test whether the work is correct, attack failure modes and hidden assumptions,
protect architecture, prevent regressions, and decide every finding
explicitly. Reviewers are routed by risk, not run as a fixed fleet. A review
that finds nothing material is a valid outcome.

## Defaults

An invocation that names no tier is T2; one that names no mode is
`AUDIT_ONLY`. Record both in the header as defaults rather than asking. Ask
only when the artifact under review is unclear.

## Review modes

| Mode | Meaning |
|------|---------|
| `AUDIT_ONLY` | Findings only. Do not edit the artifact under review. |
| `FIX_AUTHORIZED` | Findings may be fixed after triage. Do not commit unless separately authorized. |
| `FIX_AND_COMMIT_AUTHORIZED` | Findings may be fixed, validated, and committed. |

T0 records `Mode: n/a`.

## Models

Reviews run on the current session model. A T2+ review's second run differs
by frame (deep for correctness, adversarial for failure modes), not by
duplicating a frame; run it through `Agent` with a fresh context. Use another
model family only when the user asks for it; the `copilot-cli`, `codex-cli`
and `agy-cli` skills give the invocation, and a CLI that is missing or fails
is recorded as unavailable, with the fallback run noted. Record the requested
and the actual model for every run; never assume a requested model ran.

## Shared risk tiers

| Tier | Use when | Default reviewer shape |
|------|----------|------------------------|
| T0 Mechanical | Typo, formatting-only change, generated refresh, deterministic rename, or other reversible change with no listed triggers | Author checklist only; record why no trigger applies |
| T1 Normal | Contained change with low blast radius | One frame: deep for correctness or adversarial for failure-mode-heavy work |
| T2 Integrated | Cross-boundary change, persistent decision, non-trivial refactor, or meaningful process change | Deep + adversarial; add pragmatic when sequencing or rollback matters |
| T3 High-risk | Safety, security, compliance, threading, data-loss, user-impact, or hard-to-reverse architecture risk | T2 + triggered specialists, compacted to the smallest useful panel |

The median review uses 1-3 reviewers. T3 caps at 4 unless the header
justifies more.

## Reviewer routing

| Trigger | Executed reviewer or frame | Do not use when |
|---------|----------------------------|-----------------|
| Baseline correctness, coherence, evidence quality | `megamind-deep` | Purely mechanical T0 changes |
| Failure modes, regressions, misuse, hidden assumptions | `megamind-adversarial` | No plausible failure mode beyond local wording/style |
| Scope control, rollback, fix-now vs defer, practical sequencing, schedule tradeoff | Pragmatic frame | No sequencing, rollout, schedule, or cost-of-delay decision exists |
| Alternate decompositions, stuck design, new abstraction | `megamind-creative` | Mechanical changes or already constrained implementation reviews |
| Material cost, financial model, or financial data system | `megamind-financial` | No material cost or financial-calculation delta |
| Licensing of new dependencies | `code-reviewer-*` (license check) | No new or upgraded dependency |
| Compliance, data handling, legal exposure | `security-reviewer-*` for code; the adversarial frame's litigator persona otherwise | No data-handling or legal-exposure delta |

The pragmatic frame checks: smallest safe change, rollback, defer vs fix-now,
decision latency, reviewer count, and whether the process cost matches the
risk. It is a perspective applied inside whichever reviewer is already
running, not a separate skill.

Specialists are added by domain process. A skill consulted as a rule set is
not an executed reviewer; record who applied it.

## Reviewer compaction

When more than four triggers fire:

1. Group triggers by concern: correctness, failure modes, architecture,
   threading/lifecycle, security, tests, persistence, cost/scope.
2. Run at most one reviewer per concern.
3. Let adversarial cover cross-concern interactions.
4. Record unselected triggers and why they were covered or skipped.

Common Python GUI profile: deep + adversarial + a reviewer applying the
`gui-threading` and/or `python-qt-gui` skills + test review when behaviour
changed.

## Reviewer contract

Every reviewer prompt (subagent, cross-vendor CLI, or a frame applied in the
main session) states these terms. Routed skills and agents follow them over
their own standalone rules.

1. **Authority.** Reviewers are read-only in every mode. Only the orchestrator
   applies fixes, and only under `FIX_AUTHORIZED` or
   `FIX_AND_COMMIT_AUTHORIZED`.
2. **Scope.** The diff base (`git diff <base>...HEAD` plus staged and unstaged
   changes, plus untracked files from `git ls-files --others
   --exclude-standard`, read whole) or the named artifact. Pre-existing
   problems the change does not touch or worsen go under a separate "Out of
   scope" heading, not the findings.
3. **Frame.** The frame or skill to apply, its required visible sections
   (table below), and its method. A reviewer that cannot read the skill files
   (a cross-vendor CLI given only a prompt) gets the frame's Process and "As a
   reviewer frame" text and the severity calibration table pasted into the
   prompt; one that can read them gets the paths and is told to read them.
4. **Findings.** Number them `<reviewer letter>-<n>` (e.g. `B-3`) with title,
   severity, confidence, evidence strength, evidence, impact, and proposed
   fix. Severity follows [Severity calibration](#severity-calibration): it is
   set by impact, never by which checklist item fired.
5. **No quota, no invented issues.** There is no minimum number of findings;
   zero is valid when the report lists the files, checks, and attacks it
   covered. Report a finding only when a concrete input or state breaks the
   code as written, nothing (guard, test, documented contract) already handles
   it, and the change caused it. Generic advice (retries, metrics, caching) is
   a suggestion, not a finding. Never inflate a nit's severity.
6. **Model line.** The report starts with `Model: <id>` as the reviewer knows
   it; the orchestrator records it next to the requested model.

| Frame | Required visible sections |
|-------|---------------------------|
| `megamind-deep` | Assumptions (verified / inferred / uncertain), independent paths with convergence and divergence, gaps found by the critique loop, risks |
| `megamind-adversarial` | Personas used, pre-mortem, inversion, second-order effects, attacks that produced no finding |
| `megamind-creative` | Alternative decompositions considered and whether any changes the decision |
| `megamind-financial` | Section used (F0-F4 for data systems, A-E for cost or model decisions), thresholds or assumptions checked, evidence per finding |
| Pragmatic | Smallest safe change, rollback, fix-now vs defer |
| Agents | Files and checklists covered, verdict |

Agent output maps onto the ledger as follows. Agents that normally edit run
report-only as reviewers.

| Agent | Ledger mapping |
|-------|----------------|
| `code-reviewer-*`, `security-reviewer-*` | Same CRITICAL-LOW scale |
| `e2e-test-*` | Failing or missing flow test is a finding; run output is `EXECUTED` evidence |
| `refactor-cleaner-*` | SAFE / CAREFUL / RISKY is removal confidence; severity by impact |

### Orchestrator acceptance

Before a reviewer report enters the ledger:

1. Check the frame's required sections, and that each one carries evidence
   from the artifact (file:line, quoted text, or command output). A report
   that claims a frame without that is re-run once; if still missing, record
   the reviewer as "frame not applied" in the header.
2. Map every reviewer finding ID to a ledger ID (one-to-one, or merged with
   the merge recorded under `Reviewer convergence`).
3. Re-grade severity against the calibration table and note any change in
   the finding's `Evidence` line.

## Review header

Every T1+ review output starts with:

```text
Artifact reviewed: <name>
Mode: AUDIT_ONLY | FIX_AUTHORIZED | FIX_AND_COMMIT_AUTHORIZED  (default if not given)
Risk tier: T<N>  (default if not given)
Reviewers used: <list with agent IDs or CLI, requested and actual model>
Skipped/unavailable reviewers: <list with rationale>
Included triggers: <list>
Excluded triggers: <list with rationale>
```

The ledger follows the header in the chat output. A condensed table does not
replace it.

## Finding ledger

```text
ID: FINDING-<N>
Title: <short title>
Status: OPEN | RESOLVED
Severity: CRITICAL | HIGH | MEDIUM | LOW
Confidence: HIGH | MEDIUM | LOW
Evidence strength: EXECUTED | OBSERVED | INFERRED | ASSERTED
Disposition: FIX_NOW | INVESTIGATE | DEFER | ACCEPT_RISK | REJECT_FALSE_POSITIVE
Risk owner and revisit trigger: <required for DEFER or ACCEPT_RISK>
Reviewer convergence: <which reviewers agreed or disagreed>
Evidence: <file:line, command output, observation, or explicit uncertainty>
Impact: <concrete failure scenario>
Proposed fix: <specific change>
Regression guard: <test, check or doc update, or why not feasible>
```

## Evidence and confidence

Evidence strength:

- `EXECUTED`: command, test, reproduction, or check was run and output is cited.
- `OBSERVED`: source, artifact, or behaviour was directly inspected.
- `INFERRED`: conclusion follows from cited evidence but was not directly run.
- `ASSERTED`: reviewer judgment without direct supporting evidence.

Confidence: `HIGH` directly evidenced or reproduced; `MEDIUM` strongly
inferred from cited evidence; `LOW` plausible but unverified.

Low-confidence CRITICAL/HIGH findings default to `INVESTIGATE` before fixing
unless the blast radius requires immediate mitigation.

## Severity calibration

| Severity | Meaning | Default disposition |
|----------|---------|---------------------|
| CRITICAL | Severe harm, data loss, unsafe operation, security/compliance exposure, deadlock, corrupted persisted state, or no credible evidence for a consequential decision | `FIX_NOW` or immediate mitigation |
| HIGH | User-visible breakage, hard-to-reverse risk, race-prone architecture, cross-subsystem contract violation, or missing failure-mode coverage for risky behaviour | `FIX_NOW` |
| MEDIUM | Important ambiguity, maintainability risk, incomplete migration, weak test coverage, unclear ownership, or brittle integration boundary | `FIX_NOW` or `DEFER` with rationale |
| LOW | Local clarity issue, naming, minor duplication, wording ambiguity, or low-risk documentation mismatch | `FIX_NOW`, `DEFER`, or `ACCEPT_RISK` |

Smells and checklist misses are prompts for review, not automatic severity. A
MEDIUM+ finding needs a concrete failure scenario or maintenance impact.

## Disagreement handling

Resolve contradictions by evidence, not majority vote. If evidence is
ambiguous: add the narrowest reviewer or frame that matches the disputed
concern; if still unresolved, disposition as `INVESTIGATE` or `DEFER` and
record what evidence would resolve it. Never drop a contradiction silently.

## Apply-fixes and authority policy

Apply every `FIX_NOW` finding when the mode authorizes fixes. CRITICAL and
HIGH findings default to `FIX_NOW`; changing that needs an owner, a rationale
and a revisit trigger. MEDIUM and LOW findings are fixed, investigated,
deferred, accepted as risk, or rejected as false positives; never skipped
silently.

## Completion criteria

A review is complete when:

1. every requested reviewer reported or has a skipped/unavailable reason;
2. every reviewer finding ID maps to a ledger ID, and every ledger finding has
   severity, confidence, status, disposition, evidence, and guard;
3. every CRITICAL/HIGH finding is resolved, mitigated, or approved for
   defer/risk acceptance;
4. validation required by the domain process has passed or has a documented
   blocker;
5. at most one re-review pass has run unless new CRITICAL/HIGH findings
   appear. A re-review covers the fixes and their blast radius only.

## Foundry reviewer alignment

This skill routes work to reviewers the foundry ships:

- `megamind-deep`, `megamind-adversarial`, `megamind-creative`,
  `megamind-financial` skills
- `code-reviewer-*`, `security-reviewer-*`, `refactor-cleaner-*`, `e2e-test-*` agents
- `gui-threading` and `python-qt-gui` skills as rule sets for the GUI process

If a referenced reviewer is not installed in the current project, mark it as
unavailable in the review header and proceed with the closest substitute.
