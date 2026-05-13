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

## Historical intent

The original hardening instruction was to run a broad multi-reviewer pass before
committing risky phases, then triage and implement fixes across all severities.
The durable intent is:

1. test whether the work is actually correct,
2. attack failure modes and hidden assumptions,
3. protect architecture and maintainability,
4. prevent future regressions,
5. make explicit decisions about every finding.

The process routes reviewers by risk instead of always running a fixed fleet.
Most reviews should be small. High-risk or release-level work can still use a
broader holistic fleet.

## Review modes

Every review must declare its mode before findings are produced.

| Mode | Meaning |
|------|---------|
| `AUDIT_ONLY` | Findings only. Do not edit files or apply fixes. |
| `FIX_AUTHORIZED` | Findings may be fixed after triage. Do not commit unless separately authorized. |
| `FIX_AND_COMMIT_AUTHORIZED` | Findings may be fixed, validated, and committed. |

If the mode is absent, assume `AUDIT_ONLY`.

## Model strategy

Every T1+ review must declare a model strategy because model choice affects
cost, latency, and finding diversity. The user may specify exact models. If the
user does not specify models, choose a strategy from the risk tier and record
it.

| Strategy | Use when | Default |
|----------|----------|---------|
| `SINGLE_FAST` | T1 reviews where speed/cost matters more than model diversity | One fast/standard model |
| `DIVERSE_STANDARD` | T2/T3 reviews needing independent judgment without premium cost | Different standard model families where available |
| `PREMIUM_TARGETED` | Specific high-risk concern needs highest-quality judgment | One premium model on the highest-risk frame only |
| `MIXED_PREMIUM` | T4 or unusually broad T3 work | Standard models for breadth plus premium model(s) for deep/adversarial/creative synthesis |
| `USER_SPECIFIED` | User names exact models or cost constraints | Follow the user request, verify actual execution |

Prefer model diversity over duplicating the same frame on the same model. For
example, a T4 process review can use one model for deep/adversarial cost-aware
analysis and a different premium model for creative decomposition. Do not
assume a requested model actually ran: record the requested model, actual
model/tool evidence, and any substitution.

If model availability or routing is unreliable, mark the affected reviewer as
substituted or unavailable instead of claiming the intended model was used.

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

# Copilot MCP bridge (Claude Code only — gives access to Copilot's catalog
# via /copilot-ask from inside Claude Code)
copilot_mcp=no
[ -d .claude/skills/copilot-list-models ] && copilot_mcp=yes

echo "host=$host copilot_mcp=$copilot_mcp"
```

The three profiles drive which strategies are actually viable:

| Profile | What the user can actually run | Effect on prompt |
|---------|-------------------------------|------------------|
| `host=copilot-cli` | Copilot's native model catalog (GPT-5, Gemini 3, Claude 4.5/4.6, Grok, o4, etc.) plus any local tooling | All strategies viable. In `USER_SPECIFIED` / "Other", accept any Copilot-catalog model name. The bigger catalog makes `DIVERSE_STANDARD` and `MIXED_PREMIUM` cheap to satisfy. |
| `host=claude-code` + `copilot_mcp=yes` | Anthropic via current session + Agent model overrides; Copilot catalog via `/copilot-ask <model>` slash command | All strategies viable. `PREMIUM_TARGETED` / `MIXED_PREMIUM` resolve via `/copilot-ask`. |
| `host=claude-code` + `copilot_mcp=no` | Anthropic only (current session + Agent `model:` overrides). `delegate` for MiniMax if installed. | `SINGLE_FAST` and `DIVERSE_STANDARD` are fully viable. `PREMIUM_TARGETED` / `MIXED_PREMIUM` are degraded — surface this in the prompt so the user can either install Copilot MCP or pick a different strategy. |
| `host=unknown` | Conservative: assume Claude Code without MCP. | Same as the row above. |

Record the detected profile in the review header alongside the chosen
strategy.

### When to ask the user for a strategy

Prompt for **every** review (all tiers, T0 through T4). The prompt makes the
cost/diversity tradeoff visible at the start instead of buried in the
header, and prevents Claude from silently defaulting against the user's
intent on small changes.

1. **If the user already specified a strategy or specific models in their
   invocation** (e.g. `/review-process audit branch — use MIXED_PREMIUM`,
   or named exact models), record the header as `USER_SPECIFIED` and skip
   the prompt.
2. **Otherwise, before producing the review header**, call `AskUserQuestion`
   with the strategies as options. Put the tier-appropriate recommended
   strategy first and label it `(Recommended)`. Filter or annotate options
   based on the detected runtime profile (above). Treat the user's "Other"
   free-text reply as `USER_SPECIFIED` and use their wording verbatim.

Recommended default per tier (first option in the prompt):

| Tier | Recommended default |
|------|---------------------|
| T0 | `SINGLE_FAST` (mechanical change — usually skip review or one fast pass) |
| T1 | `SINGLE_FAST` |
| T2 | `DIVERSE_STANDARD` |
| T3 | `DIVERSE_STANDARD` (broader risk surface) or `PREMIUM_TARGETED` (one concentrated high-risk concern) |
| T4 | `MIXED_PREMIUM` |

#### T0 / T1 concrete model defaults (`SINGLE_FAST`)

When the recommended `SINGLE_FAST` is chosen for T0 or T1, the actual model
that runs depends on the detected runtime. These are the defaults — surface
them in the prompt's recommended-option label so the user sees the concrete
model name, not just the abstract strategy:

| Runtime | T0 / T1 default model | Notes |
|---------|-----------------------|-------|
| `host=claude-code` (any `copilot_mcp` state) | **Claude Opus 4.7** — current session model, no MCP needed | Zero extra cost: the session model is already running. Do not spawn `Agent` calls with `model: sonnet/haiku` for T0/T1 — adds latency without benefit. |
| `host=copilot-cli` | **GPT-5.4** via Copilot's catalog | Fast, cheap, and the standard mainline Copilot CLI model. |
| `host=unknown` | Same as `claude-code` (Opus 4.7, current session) | Conservative fallback. |

#### T2 concrete model defaults (`DIVERSE_STANDARD`)

`DIVERSE_STANDARD` is a hard "**at least two model runs**" strategy. If
genuine cross-vendor diversity is not reachable, fall back to two independent
runs of the same model (the value is then in independent framings/contexts
rather than family diversity, but never collapse to a single run).

| Runtime | Run A | Run B (fallback rule) |
|---------|-------|-----------------------|
| `host=claude-code` + `copilot_mcp=yes` | **Claude Opus 4.7** (current session) — deep/correctness frame | **GPT-5.4** via `/copilot-ask gpt-5.4` — adversarial/failure-modes frame |
| `host=claude-code` + `copilot_mcp=no` | **Claude Opus 4.7** (current session) — deep/correctness frame | **Claude Opus 4.7** spawned via `Agent` tool with a fresh context — adversarial/failure-modes frame. Record this as "no cross-vendor diversity available; second-run Opus 4.7" in the review header. |
| `host=copilot-cli` | **GPT-5.4** via Copilot catalog — deep/correctness frame | **Claude Opus 4.6** via Copilot catalog — adversarial/failure-modes frame |
| `host=unknown` | Same as `claude-code` + `copilot_mcp=no` | Same fallback rule |

Always assign different frames (deep vs adversarial, or whichever two the
routing table calls for) to the two runs — running the same frame twice on
two models is wasteful. The point of the dual run is independent
*perspectives*, not redundant *coverage*.

For T3-T4, model selection follows the chosen strategy (`PREMIUM_TARGETED`,
`MIXED_PREMIUM`) and the runtime profile — concrete defaults are not pinned
because the highest-tier strategies are inherently bespoke per review.

If the strategy the user chooses requires Copilot MCP, `delegate`, or a
Copilot-catalog model not reachable from the current runtime, surface this in
the review header (`Skipped/unavailable reviewers`) and substitute the
closest available reviewer rather than silently downgrading.

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
| Scope control, rollback, fix-now vs defer, practical sequencing | Pragmatic frame | No sequencing, rollout, or cost-of-delay decision exists |
| Alternate decompositions, stuck design, new abstraction, T4 review | `megamind-creative` | Mechanical changes or already constrained implementation reviews |
| Cost, licensing, compliance, business-impact, schedule tradeoff | `megamind-financial` | No material cost, compliance, licensing, or business-risk delta |

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
only for material cost, compliance, licensing, or business-impact risk.

## Review header

Every T1+ review output starts with:

```text
Artifact reviewed: <name>
Mode: AUDIT_ONLY | FIX_AUTHORIZED | FIX_AND_COMMIT_AUTHORIZED
Risk tier: T<N>
Reviewer budget: <max reviewers, max passes>
Model strategy: SINGLE_FAST | DIVERSE_STANDARD | PREMIUM_TARGETED | MIXED_PREMIUM | USER_SPECIFIED
Reviewers requested: <list>
Reviewers actually used: <list with agent IDs, model/tool evidence, or manual actor>
Requested models: <list or not specified>
Actual models: <list with evidence, or manual/no-model>
Skipped/unavailable reviewers: <list with rationale>
Included triggers: <list>
Excluded triggers: <list with rationale>
Prior state searched: <review-state sources/tags, or no prior data available>
```

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
3. every finding has severity, confidence, status, disposition, evidence, and
   guard;
4. every CRITICAL/HIGH finding is resolved, mitigated, or approved for
   defer/risk acceptance;
5. every `DEFER` or `ACCEPT_RISK` has owner, approval, and revisit trigger;
6. every `CONVERT_TO_CHECK` cites a review-state ledger entry;
7. validation required by the domain process has passed or has a documented
   blocker;
8. at most one re-review pass has run unless new CRITICAL/HIGH findings appear.

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
  `refactor-cleaner-*`, `build-error-resolver-*` agents
- `gui-threading` and `python-qt-gui` skills as rule sets for the GUI process

If a referenced reviewer is not installed in the current project, mark it as
unavailable in the review header and proceed with the closest substitute.
