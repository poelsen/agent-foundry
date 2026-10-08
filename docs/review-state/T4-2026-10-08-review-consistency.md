# T4 review record — review-process consistency change

Artifact reviewed: feature/ja_review-consistency, uncommitted changes vs master (diff snapshot 14:18; later per-role effort edits to tools/run_benchmark.py skimmed only)
Mode: AUDIT_ONLY for the review pass (user-selected); fixes applied afterwards under FIX_AUTHORIZED at the user's request, not committed
Risk tier: T4 (review-process self-review)
Reviewer budget: 2 reviewers, 1 pass (+ at most 1 fix-scoped re-review)
Model strategy: USER_SPECIFIED (MIXED_PREMIUM shape: one Opus 5.5 deep; GPT-6.1 Sol xhigh pragmatic+adversarial+creative)
Runtime profile: host=claude-code copilot_cli=yes codex_cli=yes agy_cli=yes (copilot quota exhausted → unavailable)
Reviewers requested: A — megamind-deep; B — megamind-adversarial + megamind-creative + pragmatic
Reviewers actually used: A — general-purpose subagent, model=opus, megamind-deep (applied: all required sections present); B — codex exec -m gpt-6.1-sol, reasoning xhigh, read-only sandbox, adversarial + creative + pragmatic (applied: all required sections present)
Requested models: claude-opus-5-5; gpt-6.1-sol @ xhigh
Actual models: A self-reports claude-opus-5-5; B self-reports "GPT-6" (CLI accepted -m gpt-6.1-sol)
Skipped/unavailable reviewers: copilot (monthly quota exceeded); specialist agents not run (text-only change to agents; their content was in scope for A and B)
Included triggers: review-process self-review (T4), reviewer routing, process docs, agent definitions, rubric/eval harness, CLI reference skills
Excluded triggers: financial frame as a reviewer (no material cost), GUI (no GUI code)
Prior state searched: docs/review-state/log.md tags process/* (RS-PN1–5, RS over-review note)

Reviewer → ledger mapping: A-1→F1, A-2→F2, A-3→F3, A-4→F4, A-5+B-4→F5, A-7+B-2→F6, A-8+B-3→F7, B-1→F8, B-5→F9, B-6→F10, A-6→F11, A-9→F12, A-10→F13, A-11→F14, A-12→F15, A-13→F16

## Finding ledger

ID: F1 | Tag: process/under-specified | Title: Reviewer scope excludes untracked files
Status: RESOLVED | Severity: MEDIUM | Confidence: HIGH | Evidence strength: EXECUTED
Disposition: FIX_NOW | Prevention action: NONE | Reviewer convergence: A only
Evidence: review-process/SKILL.md reviewer-contract scope; code-reviewer-*.md:11; security-reviewer-*.md:14 — all `git diff`-based; adversarial-013.yaml absent from `git diff --stat`
Impact: new, unstaged modules are outside every reviewer's scope; security-reviewer's diff-only default no longer catches them
Proposed fix: add `git ls-files --others --exclude-standard` (read whole) to the scope in all three places
Regression/process guard: none feasible beyond text

ID: F2 | Tag: process/reviewer-routing | Title: security-reviewer authority line permits edits under a review process
Status: RESOLVED | Severity: MEDIUM | Confidence: HIGH | Evidence strength: OBSERVED
Disposition: FIX_NOW | Reviewer convergence: A only
Evidence: security-reviewer-{python,typescript}.md:15 "a review process in a fix mode" vs :22 "report-only" vs review-process "read-only in every mode"
Impact: under FIX_AUTHORIZED the agent edits before triage; parallel reviewers read a moving tree
Proposed fix: "Under a review process you are read-only in every mode; outside one, fix only when the user asks for remediation"

ID: F3 | Tag: process/reviewer-routing | Title: Licensing routed to security-reviewer, which has no licensing checks
Status: RESOLVED | Severity: MEDIUM | Confidence: HIGH | Evidence strength: OBSERVED
Disposition: FIX_NOW | Reviewer convergence: A only
Evidence: review-process/SKILL.md routing row; no "licen" in security-reviewer-*; license item lives in code-reviewer-*.md Best Practices
Impact: an AGPL dependency goes to a CVE-focused agent; compaction can drop code-reviewer
Proposed fix: route licensing for code to code-reviewer-*

ID: F4 | Tag: process/reviewer-routing | Title: e2e-test agents routed as reviewers without report-only mode or ledger mapping
Status: RESOLVED | Severity: MEDIUM | Confidence: HIGH (gap) / MEDIUM (misbehaviour) | Evidence strength: OBSERVED
Disposition: FIX_NOW | Reviewer convergence: A only
Evidence: python-gui.md routes e2e-test-python-qt; agent has Write/Edit/Bash and "Write pytest-qt tests"; absent from mapping table and alignment list
Impact: GUI T3 audit can write test files; no ledger mapping
Proposed fix: report-only paragraph in e2e-test-* agents + mapping row (failure → finding, run output → EXECUTED)

ID: F5 | Tag: process/reviewer-routing | Title: Prompt-only (CLI) reviewers get frame name + headings, not the method; acceptance checks headings only; model line not required
Status: RESOLVED | Severity: MEDIUM | Confidence: MEDIUM | Evidence strength: INFERRED
Disposition: FIX_NOW | Reviewer convergence: A and B agree (A-5, B-4)
Evidence: contract item 3 and acceptance step 1 in review-process/SKILL.md; codex-cli/agy-cli "pass context in the prompt"; model evidence relies on "the agent's own report" which the contract never requests
Impact: RS-PN2 recurs as "frame headed but not applied" while RS-PN2 is marked RESOLVED
Proposed fix: payload must include the frame's Process + "As a reviewer frame" text (or a readable path with a reading requirement) and the severity table; contract item: start with `Model: <id>`; acceptance requires evidence (file:line) under each section

ID: F6 | Tag: process/under-specified | Title: Mode question skipped when a strategy is named; T0 mode undefined
Status: RESOLVED | Severity: MEDIUM | Confidence: HIGH | Evidence strength: OBSERVED
Disposition: FIX_NOW | Reviewer convergence: A (LOW) and B (MEDIUM) agree on the defect; graded MEDIUM (repeats the RS-PN1 incident)
Evidence: review-process/SKILL.md "When to ask the user" step 1 vs step 2 "Otherwise"; T0 "do not prompt"
Impact: `/review-process … DIVERSE_STANDARD` silently runs AUDIT_ONLY
Proposed fix: build the question batch from independently missing fields; T0 records `Mode: n/a`

ID: F7 | Tag: process/under-specified | Title: AUDIT_ONLY "do not edit files" conflicts with the mandatory T2+ ledger file
Status: RESOLVED | Severity: MEDIUM | Confidence: HIGH | Evidence strength: OBSERVED
Disposition: FIX_NOW | Reviewer convergence: A (LOW) and B (MEDIUM); graded MEDIUM — this very review hit it (ledger written to the scratchpad instead)
Evidence: review-process/SKILL.md Review modes table vs the new "write the header and the full ledger to docs/review-state/" paragraph
Impact: an audit must either break its mode or skip the ledger (RS-PN3 regression)
Proposed fix: modes govern the artifact under review; review records in docs/review-state/ are always written; update the template README

ID: F8 | Tag: process/reviewer-routing | Title: Financial frame keeps a competing severity rule
Status: RESOLVED | Severity: MEDIUM | Confidence: HIGH | Evidence strength: OBSERVED
Disposition: FIX_NOW | Reviewer convergence: B only (A-10 is adjacent, see F13)
Evidence: megamind-financial "As a reviewer frame" says derive severity from F3/F4; F3 ratio table vs F4 boundary definition; caller grades by impact
Impact: same error graded differently by frame and caller
Proposed fix: F3/F4 supply magnitude/proximity/blast-radius evidence; final severity from the caller's calibration table

ID: F9 | Tag: docs/drift | Title: agy canonical example hides the empty-response failure
Status: RESOLVED | Severity: MEDIUM | Confidence: HIGH | Evidence strength: OBSERVED
Disposition: FIX_NOW | Reviewer convergence: B only
Evidence: agy-cli/SKILL.md canonical pipeline prints `response or error`; new paragraph says empty response = failed run
Impact: `{"status":"SUCCESS","response":""}` prints `None` and exits 0
Proposed fix: parser requires SUCCESS and non-blank response, exits non-zero otherwise

ID: F10 | Tag: process/reviewer-routing | Title: CLI default model may be Claude, defeating DIVERSE_STANDARD's non-Claude run
Status: RESOLVED | Severity: LOW (re-graded from MEDIUM: a recorded same-vendor second run is an allowed fallback) | Confidence: MEDIUM | Evidence strength: INFERRED
Disposition: FIX_NOW | Reviewer convergence: B only
Evidence: review-process Concrete runs ("CLI default"); copilot-cli allows default/auto
Proposed fix: pick a different model family when the default's family is unknown or Claude; else record degraded diversity

ID: F11 | Tag: process/under-specified | Title: Frame sections and agent texts don't fully match the contract tables
Status: RESOLVED | Severity: LOW | Confidence: HIGH | Evidence strength: OBSERVED
Disposition: FIX_NOW | Reviewer convergence: A only
Evidence: deep frame omits "risks"; deep frame silent on scope gate / Rule 5 / paths-as-designs; report-only texts ask no verdict; code-reviewer CRITICAL/HIGH lists omit deadlock/race/compliance
Proposed fix: deep frame adds risks and "paths = independent ways to verify the change; scope gate and Rule 5 don't apply"; agents: "under a review process, use its calibration and end with a verdict"

ID: F12 | Tag: process/under-specified | Title: build-error-resolver report-only mode may run auto-fixing lint scripts
Status: RESOLVED | Severity: LOW | Confidence: MEDIUM | Evidence strength: INFERRED
Disposition: FIX_NOW | Reviewer convergence: A only
Proposed fix: "check-only forms; read script definitions before running them"

ID: F13 | Tag: process/reviewer-routing | Title: Financial frame assumes Section F for every route
Status: RESOLVED | Severity: LOW | Confidence: MEDIUM | Evidence strength: OBSERVED
Disposition: FIX_NOW | Reviewer convergence: A only
Proposed fix: data systems → F0-F4; cost/model decisions → matching A–E section with assumptions + sensitivity; adjust the required-sections row

ID: F14 | Tag: process/under-specified | Title: RS-PN1–5 closed on "text exists" rather than behavioural verification
Status: RESOLVED | Severity: LOW | Confidence: HIGH | Evidence strength: OBSERVED
Disposition: FIX_NOW | Reviewer convergence: A only
Proposed fix: keep behavioural Verification text; close RS-PN1–4 citing this T4 record (first run showing frame sections + ID mapping); keep RS-PN5 OPEN until a post-change adversarial-013 run passes

ID: F15 | Tag: tests/missing-failure-path | Title: Errored benchmark runs silently drop out of saved results
Status: RESOLVED | Severity: LOW | Confidence: MEDIUM | Evidence strength: OBSERVED
Disposition: FIX_NOW | Reviewer convergence: A only
Proposed fix: record `errors: n` per mode in JSON and summary

ID: F16 | Tag: tests/mock-integration | Title: adversarial-013 "no material flaw" premise has a real residual weakness
Status: RESOLVED | Severity: LOW | Confidence: MEDIUM | Evidence strength: INFERRED
Disposition: FIX_NOW | Reviewer convergence: A only
Evidence: requests' timeout bounds connect and per-read, not total; main() checks several services
Proposed fix: state that main() checks one service, or tell the judge a LOW/MEDIUM note on total-time bounding is acceptable

## Closure
Review pass ran AUDIT_ONLY: 0 CRITICAL, 0 HIGH, 9 MEDIUM, 7 LOW. The user then authorized fixes; all 16 were applied in the working tree (not committed) and validated with the full pytest suite, tools/validate.py and a claude/codex/agy deploy smoke test. RS-PN1–4 close with this record as their first passing run; RS-PN5 stays OPEN until the reworked adversarial-013 passes. Both reviewers: the change makes the process substantially more coherent, no deploy/test/harness regression; megamind structure still reasonable, with benchmark support for depth and scope control more than for changed conclusions.
