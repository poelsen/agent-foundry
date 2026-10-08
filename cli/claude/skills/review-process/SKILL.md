---
name: review-process
description: Tiered review process. Risk tiers T0-T4, modes, reviewer routing to megamind/agent reviewers, finding ledger, persistent state. Activate on /review-process or before risky commits/PRs/decisions.
model: opus
---

# Review Process

This is the canonical entry point for tiered reviews. It defines the shared risk
tiers, review modes, routing rules, finding ledger, and closure policy. The
sibling files in this skill add domain-specific checks only.

## Load applicable sub-files before reviewing

Claude Code only auto-loads `SKILL.md`. The sub-files (`general.md`,
`software.md`, `python.md`, `python-non-gui.md`, `python-gui.md`) are **not**
loaded until you Read them explicitly. Before producing the review header:

1. Use the Process Selection table below to determine which sub-files apply.
2. Read every applicable sub-file with the Read tool. Always include
   `general.md` plus every more-specific file whose trigger fires — they are
   additive, not exclusive.
3. Only after the sub-files are loaded, produce the review header and findings.

Skipping this step silently drops the domain-specific checklists, severity
adjustments, and output addenda — the review will look correct but apply only
the canonical core.

## Process selection

Always start with the general process, then add every more-specific process
whose trigger applies. Do not choose only the most-specific file.

| Work under review | Apply these processes |
|-------------------|-----------------------|
| Non-software decision, plan, document, policy, or operation | [General](general.md) |
| Software change in any language | General + [Software](software.md) |
| Python code, packaging, tests, scripts, services, or libraries | General + Software + [Python](python.md) |
| Python CLI, worker, service, library, or other non-GUI runtime | General + Software + Python + [Python non-GUI](python-non-gui.md) |
| PySide6/PyQt/Qt desktop GUI work | General + Software + Python + [Python GUI](python-gui.md) |
| Review-process documentation itself | General + every governed domain process affected by the change |

Treat GUI and non-GUI as concern modules, not a rigid tree. If a change touches
multiple concerns, apply all relevant modules and compact reviewer selection as
described below.

## Intent

Test whether the work is correct, attack failure modes and hidden assumptions,
protect architecture, prevent regressions, and decide every finding explicitly.
Reviewers are routed by risk, not run as a fixed fleet: most reviews are small,
and release-level work can use a broader one. A review that finds nothing
material is a valid outcome, not a failed review.

## Review modes

Every review must declare its mode before findings are produced.

| Mode | Meaning |
|------|---------|
| `AUDIT_ONLY` | Findings only. Do not edit the artifact under review or apply fixes. |
| `FIX_AUTHORIZED` | Findings may be fixed after triage. Do not commit unless separately authorized. |
| `FIX_AND_COMMIT_AUTHORIZED` | Findings may be fixed, validated, and committed. |

Modes govern the artifact under review. The review's own record in
`docs/review-state/` is written in every mode, `AUDIT_ONLY` included.

If the invocation does not name a mode, ask for it (see "When to ask the
user"). Only when nobody can be asked (a subagent or non-interactive run) does
the mode default to `AUDIT_ONLY`; record that default in the header. T0
records `Mode: n/a`.

## Model strategy

Every T1+ review declares a model strategy; it drives cost, latency, and
finding diversity.

| Strategy | Use when | Default |
|----------|----------|---------|
| `SINGLE_FAST` | T1 reviews where speed/cost matters more than model diversity | The current session model |
| `DIVERSE_STANDARD` | T2/T3 reviews needing independent judgment without premium cost | At least two runs, different model families where available |
| `PREMIUM_TARGETED` | Specific high-risk concern needs highest-quality judgment | One premium model on the highest-risk frame only |
| `MIXED_PREMIUM` | T4 or unusually broad T3 work | Standard models for breadth plus premium model(s) for deep/adversarial/creative synthesis |
| `USER_SPECIFIED` | User names exact models or cost constraints | Follow the user request, verify actual execution |

Prefer model diversity over duplicating the same frame on the same model. Do
not assume a requested model actually ran: record the requested model, the
actual model as reported by the run (CLI output or the agent's own report), and
any substitution. Model versions are deliberately not pinned here; the current
session model and each CLI's default move faster than this file.

### Runtime detection (do this before prompting)

The set of models the skill can actually route to depends on the host running
this conversation. Detect the runtime with this bash snippet **before** the
prompt step:

```bash
# Host detection
if [ "${CLAUDECODE:-}" = "1" ]; then
    host=claude-code
elif [ -n "${COPILOT_CLI:-}${GH_COPILOT_CLI:-}${COPILOT_AGENT:-}" ]; then
    host=copilot-cli
else
    host=unknown
fi

# Local cross-vendor CLIs — the ONLY ways to run non-Claude models. Each has
# a reference skill with the exact invocation contract:
#   copilot → Copilot catalog (GPT, Gemini, Grok, …)   see `copilot-cli`
#   codex   → OpenAI models directly                   see `codex-cli`
#   agy     → Google Gemini models                     see `agy-cli`
copilot_cli=no
command -v copilot >/dev/null 2>&1 && copilot --version >/dev/null 2>&1 && copilot_cli=yes
codex_cli=no
command -v codex >/dev/null 2>&1 && codex --version >/dev/null 2>&1 && codex_cli=yes
agy_cli=no
command -v agy >/dev/null 2>&1 && agy --version >/dev/null 2>&1 && agy_cli=yes

echo "host=$host copilot_cli=$copilot_cli codex_cli=$codex_cli agy_cli=$agy_cli"
```

> **Hard requirement:** a non-Claude reviewer needs one of these local CLIs;
> there is no other bridge. A CLI that is missing or fails (quota exhausted,
> auth error, model rejected) is unavailable for this review: record its error
> verbatim and fall back per `DIVERSE_STANDARD`.

| Profile | What the user can actually run | Effect on prompt |
|---------|-------------------------------|------------------|
| `host=copilot-cli` | Copilot's native model catalog directly | All strategies viable. In `USER_SPECIFIED` / "Other", accept any Copilot-catalog model name. |
| `host=claude-code` + any cross-vendor CLI | Anthropic via the current session + Agent model overrides; non-Claude models via the `copilot-cli`, `codex-cli` or `agy-cli` skill | All strategies viable within the vendors present. Prefer `codex` for GPT and `agy` for Gemini. |
| `host=claude-code` + no cross-vendor CLI | Anthropic only (current session + Agent `model:` overrides) | `SINGLE_FAST` and `DIVERSE_STANDARD` still viable (same-vendor fallback). `PREMIUM_TARGETED` / `MIXED_PREMIUM` with a non-Claude model are degraded — say so in the prompt so the user can install a CLI or pick a different strategy. |
| `host=unknown` | Conservative: assume Claude Code without a cross-vendor CLI. | Same as the row above. |

Record the detected profile in the review header (`Runtime profile:`).

### When to ask the user

Prompt for every T1+ review. T0 is the author checklist only: record the
tier and why no trigger applies, and do not prompt.

Before producing the review header, make one `AskUserQuestion` call holding
each question whose answer the invocation did not already give:

- **Strategy** — skipped when the invocation names a strategy or exact models
  (e.g. `/review-process audit branch — use MIXED_PREMIUM`); record
  `USER_SPECIFIED`. Otherwise list the strategies with the tier-appropriate
  recommendation first, labelled `(Recommended)`, filtered or annotated by the
  runtime profile. Treat an "Other" free-text reply as `USER_SPECIFIED` and use
  the user's wording verbatim.
- **Mode** — skipped when the invocation names one. Otherwise offer
  `AUDIT_ONLY`, `FIX_AUTHORIZED`, `FIX_AND_COMMIT_AUTHORIZED` with no
  recommendation; the mode is the user's authority call.

If both were given, make no call.

Recommended strategy per tier:

| Tier | Recommended default |
|------|---------------------|
| T1 | `SINGLE_FAST` |
| T2 | `DIVERSE_STANDARD` |
| T3 | `DIVERSE_STANDARD` (broader risk surface) or `PREMIUM_TARGETED` (one concentrated high-risk concern) |
| T4 | `MIXED_PREMIUM` |

### Concrete runs

`SINGLE_FAST` runs on the current session model. Do not spawn `Agent` calls
with a smaller model for T1 — it adds latency without benefit.

`DIVERSE_STANDARD` is a hard "**at least two runs**" strategy with different
frames (deep/correctness for run A, adversarial/failure-modes for run B, or
whichever two the routing table calls for — never the same frame twice):

| Runtime | Run A | Run B |
|---------|-------|-------|
| `host=claude-code` + a working cross-vendor CLI | Current session model | A non-Claude model through that CLI's skill: the user-named model, else the CLI default when its family is known to differ from run A, else a different-family model from the CLI's catalog |
| `host=claude-code` + no working cross-vendor CLI | Current session model | The session model again via `Agent` with a fresh context; record "no cross-vendor diversity available" and why |
| `host=copilot-cli` | Current session model | A catalog model from a different family (never `auto`, which may pick the same family) |
| `host=unknown` | As `claude-code` without a CLI | Same fallback |

For T3-T4, model selection follows the chosen strategy and runtime profile;
the highest-tier strategies are bespoke per review.

If the chosen strategy needs a model the runtime cannot serve, record it under
`Skipped/unavailable reviewers` and substitute the closest available run per
the `DIVERSE_STANDARD` fallback rather than silently downgrading or pretending
the intended model ran.

## Shared risk tiers

| Tier | Use when | Default reviewer shape |
|------|----------|------------------------|
| T0 Mechanical | Typo, formatting-only change, generated refresh, deterministic rename, or other reversible change with no listed triggers | Author checklist only; record why no trigger applies |
| T1 Normal | Contained change with low blast radius | One reviewer/frame: deep for correctness or adversarial for failure-mode-heavy work |
| T2 Integrated | Cross-boundary change, persistent decision, non-trivial refactor, or meaningful process change | Deep + adversarial; add pragmatic when sequencing or rollback matters |
| T3 High-risk | Safety, security, compliance, threading, data-loss, user-impact, or hard-to-reverse architecture risk | T2 + triggered specialists, compacted to the smallest useful panel |
| T4 Release/post-incident/process | Milestone hardening, post-incident review, recurring regressions, architectural reset, or review-process self-review | Deep + adversarial + creative + pragmatic, plus only triggered specialists |

The median review should use 1-3 reviewers. T3 should normally cap at 4
reviewers unless the review header justifies more. T4 is holistic, but still
records included and excluded reviewers with reasons.

## Reviewer routing

| Trigger | Executed reviewer or frame | Do not use when |
|---------|----------------------------|-----------------|
| Baseline correctness, coherence, evidence quality | `megamind-deep` | Purely mechanical T0 changes |
| Failure modes, regressions, misuse, hidden assumptions | `megamind-adversarial` | No plausible failure mode beyond local wording/style |
| Scope control, rollback, fix-now vs defer, practical sequencing, schedule tradeoff | Pragmatic frame | No sequencing, rollout, schedule, or cost-of-delay decision exists |
| Alternate decompositions, stuck design, new abstraction, T4 review | `megamind-creative` | Mechanical changes or already constrained implementation reviews |
| Material cost, financial model, or financial data system | `megamind-financial` | No material cost or financial-calculation delta |
| Licensing of new dependencies | `code-reviewer-*` (license check) | No new or upgraded dependency |
| Compliance, data handling, legal exposure | `security-reviewer-*` for code; the adversarial frame's litigator persona otherwise | No data-handling or legal-exposure delta |

The pragmatic frame checks: smallest safe change, rollback, defer vs fix-now,
decision latency, reviewer count, and whether the process cost matches the
risk. It is a perspective, not a separate skill — apply it inside whichever
reviewer is already running.

Specialists are added by domain process. Skills/rule sets are not the same as
executed reviewers; if a skill is consulted, record who applied it.

## Reviewer compaction

Routing is not additive without limit. When more than four triggers fire:

1. Group triggers by concern: correctness, failure modes, architecture,
   threading/lifecycle, security, tests, persistence, cost/scope.
2. Run at most one reviewer per concern.
3. Let adversarial cover cross-concern interactions.
4. Record unselected triggers and why they were covered or intentionally
   skipped.

Common Python GUI profile: deep + adversarial + a reviewer applying the
`gui-threading` and/or `python-qt-gui` skills + test/TDD review when behavior
changed.

## Reviewer contract

Every reviewer prompt (subagent, cross-vendor CLI, or a frame applied in the
main session) states these terms. Routed skills and agents follow them over
their own standalone rules (confirmation stops, edit steps, output formats).

1. **Authority.** Reviewers are read-only in every mode. Only the orchestrator
   applies fixes, and only under `FIX_AUTHORIZED` or
   `FIX_AND_COMMIT_AUTHORIZED`.
2. **Scope.** The diff base (`git diff <base>...HEAD` plus staged and unstaged
   changes, plus untracked files from `git ls-files --others
   --exclude-standard`, read whole) or the named artifact. Pre-existing problems
   the change does not touch or worsen go under a separate "Out of scope"
   heading, not the findings.
3. **Frame.** The frame or skill to apply, its required visible sections
   (table below), and its method. A reviewer that cannot read the skill files
   (a cross-vendor CLI given only a prompt) gets the frame's Process and "As a
   reviewer frame" text and the severity calibration table pasted into the
   prompt; one that can read them gets the paths and is told to read them.
4. **Findings.** Number them `<reviewer letter>-<n>` (e.g. `B-3`) with title,
   severity, confidence, evidence strength, evidence, impact, and proposed fix.
   Severity follows [Severity calibration](#severity-calibration): it is set by
   impact, never by which checklist item fired.
5. **No quota, no invented issues.** There is no minimum number of findings;
   zero is valid when the report lists the files, checks, and attacks it
   covered. Review prompts invite invented problems, most of all on a correct
   change, so report a finding only when a concrete input or state breaks the
   code as written, nothing (guard, test, documented contract) already handles
   it, and the change caused it. Generic advice (retries, metrics, caching) is a
   suggestion, not a finding. Never inflate a nit's severity.
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
| `code-reviewer-*`, `security-reviewer-*` | Same CRITICAL–LOW scale |
| `e2e-test-*` | Failing or missing flow test → finding; run output → `EXECUTED` evidence |
| `tdd-guide-*` | Missing or weak test → finding; MEDIUM+ only with a concrete regression scenario |
| `refactor-cleaner-*` | SAFE / CAREFUL / RISKY is removal confidence → `Confidence`; severity by impact |
| `architect-*` | Red flag → finding; severity by impact |
| `build-error-resolver-*` | Tool output → `EXECUTED` evidence |

### Orchestrator acceptance

Before a reviewer report enters the ledger:

1. Check the frame's required sections, and that each one carries evidence
   from the artifact (file:line, quoted text, or command output), not just a
   heading. A report that claims a frame without that is re-run once; if it is
   still missing, record the reviewer as "frame not applied" in the header.
2. Map every reviewer finding ID to a ledger ID (one-to-one, or merged with the
   merge recorded under `Reviewer convergence`). No reviewer finding leaves the
   review without a ledger ID.
3. Re-grade severity against the calibration table and note any change in the
   finding's `Evidence` line.

## T4 requirements

T4 reviews are holistic and must include:

- mode, risk tier, reviewer budget, and maximum re-review passes;
- model strategy, requested models, actual models, and substitutions;
- included reviewers and excluded reviewers with reasons;
- prior review ledgers or an explicit "no prior data available" note;
- relevant incidents, escaped defects, PR findings, backlog/process items, and
  open deferrals where available;
- recurring-finding tags searched;
- contradictions and how they were resolved or deferred;
- a final closure statement.

Default T4 frames are deep, adversarial, creative, and pragmatic. Add financial
only for material cost or financial-calculation risk.

## Review header

Every T1+ review output starts with:

```text
Artifact reviewed: <name>
Mode: AUDIT_ONLY | FIX_AUTHORIZED | FIX_AND_COMMIT_AUTHORIZED
Risk tier: T<N>
Reviewer budget: <max reviewers, max passes>
Model strategy: SINGLE_FAST | DIVERSE_STANDARD | PREMIUM_TARGETED | MIXED_PREMIUM | USER_SPECIFIED
Runtime profile: host=<…> copilot_cli=<yes|no> codex_cli=<yes|no> agy_cli=<yes|no>
Reviewers requested: <list>
Reviewers actually used: <list with agent IDs, model/tool evidence, or manual actor>
Requested models: <list or not specified>
Actual models: <list with evidence, or manual/no-model>
Skipped/unavailable reviewers: <list with rationale>
Included triggers: <list>
Excluded triggers: <list with rationale>
Prior state searched: <review-state sources/tags, or no prior data available>
```

For T2+ reviews, write the header and the full ledger to
`docs/review-state/T<N>-<YYYY-MM-DD>-<slug>.md` (in every mode, see Review
modes) and summarise it in chat. A condensed chat table does not replace the
ledger.

## Finding ledger

Use this shape for every finding:

```text
ID: FINDING-<N>
Tag: <domain/class tag, e.g. docs/drift or tests/mock-integration>
Title: <short title>
Status: OPEN | RESOLVED | EXPIRED
Severity: CRITICAL | HIGH | MEDIUM | LOW
Confidence: HIGH | MEDIUM | LOW
Evidence strength: EXECUTED | OBSERVED | INFERRED | ASSERTED
Disposition: FIX_NOW | INVESTIGATE | DEFER | ACCEPT_RISK | REJECT_FALSE_POSITIVE
Prevention action: NONE | CONVERT_TO_CHECK(<review-state ledger entry>)
Risk owner: <required for DEFER or ACCEPT_RISK on HIGH/CRITICAL>
Approval: <required for DEFER or ACCEPT_RISK on HIGH/CRITICAL>
Revisit trigger: <required for DEFER or ACCEPT_RISK>
Reviewer convergence: <which reviewers agreed or disagreed>
Evidence: <source, file/path line range, command output, observation, or explicit uncertainty>
Impact: <concrete failure scenario>
Proposed fix: <specific change>
Regression/process guard: <test/check/process/doc update, or why not feasible>
```

`CONVERT_TO_CHECK` is a prevention action, not a substitute for remediation. A
live defect still needs a remediation disposition.

## Evidence and confidence

Evidence strength:

- `EXECUTED`: command, test, reproduction, or check was run and output is cited.
- `OBSERVED`: source, artifact, or behavior was directly inspected.
- `INFERRED`: conclusion follows from cited evidence but was not directly run.
- `ASSERTED`: reviewer judgment without direct supporting evidence.

Confidence:

- `HIGH`: directly evidenced or reproduced.
- `MEDIUM`: strongly inferred from cited evidence.
- `LOW`: plausible but unverified.

Low-confidence critical/high findings default to `INVESTIGATE` before fixing
unless the blast radius requires immediate mitigation.

## Severity calibration

| Severity | Meaning | Default disposition |
|----------|---------|---------------------|
| CRITICAL | Severe harm, data loss, unsafe operation, security/compliance exposure, deadlock, corrupted persisted state, or no credible evidence for a consequential decision | `FIX_NOW` or immediate mitigation |
| HIGH | User-visible breakage, hard-to-reverse risk, race-prone architecture, cross-subsystem contract violation, or missing failure-mode coverage for risky behavior | `FIX_NOW` |
| MEDIUM | Important ambiguity, maintainability risk, incomplete migration, weak test coverage, unclear ownership, or brittle integration boundary | `FIX_NOW` or `DEFER` with rationale |
| LOW | Local clarity issue, naming, minor duplication, wording ambiguity, or low-risk documentation mismatch | `FIX_NOW`, `DEFER`, or `ACCEPT_RISK` |

Smells and checklist misses are prompts for review, not automatic severity. A
MEDIUM+ finding needs a concrete failure scenario or maintenance impact.

## Disagreement handling

Resolve contradictions by evidence, not majority vote. If evidence is
ambiguous:

1. add the narrowest reviewer/frame that matches the disputed concern;
2. if still unresolved, disposition as `INVESTIGATE` or `DEFER`;
3. record what evidence would resolve it;
4. never silently drop the contradiction in T3/T4 reviews.

## Apply-fixes and authority policy

Apply every finding whose disposition is `FIX_NOW` when the review mode
authorizes fixes. Critical and high-severity findings default to `FIX_NOW`;
changing that requires explicit owner, approval, rationale, and revisit
trigger.

Do not silently skip medium or low findings. They must be fixed, investigated,
deferred, accepted as risk, rejected as false positives, or paired with a
prevention action.

## Completion criteria

A review is complete when:

1. all requested reviewers either reported or have a skipped/unavailable
   reason;
2. model strategy and actual model/tool evidence are recorded;
3. every reviewer finding ID maps to a ledger ID, and every ledger finding has
   severity, confidence, status, disposition, evidence, and guard;
4. every CRITICAL/HIGH finding is resolved, mitigated, or approved for
   defer/risk acceptance;
5. every `DEFER` or `ACCEPT_RISK` has owner, approval, and revisit trigger;
6. every `CONVERT_TO_CHECK` cites a review-state ledger entry;
7. validation required by the domain process has passed or has a documented
   blocker;
8. at most one re-review pass has run unless new CRITICAL/HIGH findings appear.
   A re-review pass covers the fixes and their blast radius only; frames do not
   re-run a full attack on unchanged work.

## Review state

Persistent review state lives in the **project under review**, at
`docs/review-state/`. Use it for recurring-finding tags, converted checks,
deferrals, risk acceptances, and review-process self-audit notes.

On first use, seed the directory by copying the templates shipped with this
skill. The commands below are **seed-on-first-use only** — they are guarded so
re-running them never overwrites an existing `log.md` or `README.md`:

```bash
mkdir -p docs/review-state
[ -f docs/review-state/README.md ] || cp .claude/skills/review-process/review-state-template/README.md docs/review-state/README.md
[ -f docs/review-state/log.md ]    || cp .claude/skills/review-process/review-state-template/log.md docs/review-state/log.md
```

Do **not** remove the `[ -f ... ] ||` guards or run an unconditional `cp` —
`log.md` is the durable record of every accepted risk, deferral, and converted
check, and an unguarded copy would silently destroy it.

After seeding, append entries to `docs/review-state/log.md` using the shape
documented in its README. Before T2+ reviews, search the log for tags matching
the scope. Before T4 reviews, also inspect all OPEN entries and state whether
each was resolved, expired, or remains accepted/deferred.

## Foundry reviewer alignment

This skill routes work to reviewers that Foundry already ships:

- `megamind-deep`, `megamind-adversarial`, `megamind-creative`,
  `megamind-financial` skills
- `code-reviewer-*`, `security-reviewer-*`, `tdd-guide-*`, `architect-*`,
  `refactor-cleaner-*`, `build-error-resolver-*`, `e2e-test-*` agents
- `gui-threading` and `python-qt-gui` skills as rule sets for the GUI process

If a referenced reviewer is not installed in the current project, mark it as
unavailable in the review header and proceed with the closest substitute.
