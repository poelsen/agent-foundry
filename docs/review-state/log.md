# Review State Log

Append review-state entries here. Keep entries concise and searchable.

See `README.md` (in this directory) for the required entry shape and the
recommended tag list.

<!-- Entries below this line. Example:

## EXAMPLE-001: Example process note

Type: PROCESS_NOTE
Source review: <artifact or review ID>
Tag: process/over-review
Status: OPEN
Owner: not-assigned
Trigger: next review-process structural change
Evidence: <link/path/command/output>
Action: <what was done or must be done>
Verification: <how to prove the check/action still works>

-->

## RS-F1: Update turns on formatter hooks that rewrite whole files

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: upgrade/hooks
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: B: black-configured project, one-line edit → 58+/21− ruff rewrite after /update-foundry (old matcher never fired; deploy.py matcher fix makes auto-selected hooks run)
Action: Formatters and mypy run only where the project configures the tool (`has_config` in _edited-files.sh walks up for ruff.toml/.ruff.toml/[tool.ruff], .prettierrc*/prettier.config.*/package.json "prettier", mypy.ini/[mypy]/[tool.mypy]); setup summary + README upgrade notes explain it
Verification: tests/test_hooks.py::test_hook_skips_projects_without_tool_config, ::test_tool_config_found_in_parent_directory

## RS-F2: Copies of foundry files keep the marker and get deleted

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: data-loss/prune
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: B + orchestrator: cp -r .agents/skills/megamind-deep team-deep; cp architect-python.toml team-architect.toml → both deleted on next init
Action: Every prune requires a foundry-owned name (catalog or retired) AND the marker: shared skills, overflow rules, Codex agents, agy agents
Verification: test_shared_outputs.py::test_copied_skill_under_new_name_survives_prune; test_codex_adapter.py/test_agy_adapter.py::test_copied_agent_survives_prune

## RS-F3: Codex MCP merge can write invalid config.toml or crash

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: correctness/toml-merge
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: orchestrator: user `mcp_servers = { mine = {...} }` + memory → "Cannot declare ('mcp_servers','memory') twice"; A: `mcp_servers = 1` → TypeError mid-run
Action: Non-table mcp_servers → warn + skip; merged text re-parsed with tomllib before writing, refused if invalid
Verification: test_codex_adapter.py::test_merge_never_writes_invalid_toml[inline table|scalar|dotted keys]

## RS-F4: Codex hook command fails (exit 127) in nested projects

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: hooks/codex-path
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: A, B: mono/.git + mono/svc/.codex, run from svc → `…/mono/.codex/hooks/agent-foundry/…: No such file`, exit 127
Action: `sh -c` finder walks up from $PWD to .codex/hooks/agent-foundry/<script>; quiet exit 0 when absent; independent of the user's login shell
Verification: test_codex_adapter.py::test_hook_command_finds_scripts_from_nested_dirs

## RS-F5: AGENTS.md symlinked to CLAUDE.md: shared block overwrites the Claude header

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: shared/agents-md
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: A, B: `ln -s CLAUDE.md AGENTS.md`; init claude+codex → CLAUDE.md lost its rule index, gained 7 embedded rule bodies, flips every run
Action: write_agents_md skips the block (with a note) when Claude is a target and AGENTS.md samefile CLAUDE.md
Verification: test_shared_outputs.py::test_symlinked_agents_md_keeps_claude_header

## RS-F6: User-ordered --clis lets Codex write before Claude aborts; duplicates run twice

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: correctness/ordering
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: A: unmarked CLAUDE.md + `--clis codex,claude` → .codex/ written, then Claude skips the project; no manifest
Action: _select_clis returns canonical ADAPTERS order, deduplicated
Verification: test_adapters.py::test_select_clis_canonical_order_without_duplicates, ::test_claude_abort_leaves_no_other_cli_files

## RS-F7: Non-Claude runs never write VERSION

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: contract/version-tracking
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: A: `init --clis codex` → .claude/ = {setup-manifest.json}; discover_projects/has_setup and the downgrade guard key on VERSION
Action: cmd_init writes .claude/VERSION for every target (moved out of the Claude adapter)
Verification: test_agy_adapter.py::test_version_written_for_non_claude_targets

## RS-F8: Check hooks cost time but never report to the agent; npx tsc can download a package

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: hooks/feedback+perf
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: B: scripts exit 0 with stderr only (Claude/Codex show stderr only on exit 2); `npx tsc` without local typescript fetches the unrelated `tsc` package
Action: mypy/tsc/cargo errors returned as one hookSpecificOutput.additionalContext object (Claude/Codex), stderr for Antigravity; mypy gated on config; `npx --no-install tsc`; cargo uses --manifest-path of the enclosing crate
Verification: test_hooks.py::test_check_errors_reach_the_agent_as_context, ::test_tsc_check_uses_local_compiler_and_reports_edited_file, ::test_antigravity_gets_json_object_and_workspace_cwd

## RS-F9: MCP ownership differs per CLI: agy freezes stale entries, Codex/.mcp.json reset filled-in keys

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: ownership/mcp
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: A: catalog args changed → agy "Kept the project's own …" and never updated/removed; B: real key in Codex block reset to YOUR_FIRECRAWL_KEY_HERE (.mcp.json reset pre-existing on master)
Action: deploy.reconcile_mcp_servers: owned while equal to the current or last-recorded rendering (manifest `deployed_mcp`), modulo filled-in placeholder values; owned entries updated/removed, others kept; keep_filled_placeholders in .mcp.json, agy and the Codex block; unparseable .mcp.json now left alone instead of overwritten
Verification: test_agy_adapter.py::test_filled_in_api_key_survives_updates, ::test_otherwise_edited_server_is_the_projects, ::test_catalog_change_reaches_deployed_entry; test_codex_adapter.py::test_filled_in_key_in_managed_block_survives; test_shared_outputs.py::test_mcp_json_reconciles_with_recorded_state

## RS-F10: Dropping a target leaves its config active and never updated

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: lifecycle/undeploy
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: B: re-run with --clis claude after claude,codex,agy → all .codex/ and .agents/ content stays, manifest forgets it
Action: CliAdapter.undeploy() (Codex/agy: deploy an empty selection; Claude: notice only); shared outputs no remaining target reads are removed (AGENTS.md block, overflow rules, .agents/skills, .mcp.json entries) with the same ownership proofs
Verification: test_codex_adapter.py::test_dropping_codex_removes_its_config; test_agy_adapter.py::test_dropping_agy_removes_its_config

## RS-F11: Codex and agy hooks can't run on Windows

Type: DEFERRAL
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: hooks/windows
Status: OPEN
Owner: not-assigned
Trigger: first Windows user report, or a Windows CI runner
Evidence: B: no commandWindows → cmd.exe /C runs `"$(git rev-parse …)"`; agy `cmd /c "x.sh; echo '{}'"` has no `;` separator
Action: Mitigated without Windows verification: Codex commandWindows = `bash -c '<finder>'` (Git Bash); agy command `bash <script>` (valid in sh and cmd) with the helper printing `{}` itself; README documents the Git Bash + jq requirement
Verification: Run the Codex and agy hooks on Windows with Git Bash + jq

## RS-F12: Claude hook command relative to cwd; agy `enabled: false` reset

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: hooks/paths
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: B: `.claude/hooks/library/x.sh` from a subdirectory → exit 127; agy entry recreated without the user's enabled flag
Action: `"$CLAUDE_PROJECT_DIR"/.claude/hooks/library/<script>`; agy `enabled` carried over
Verification: test_hooks.py::test_every_hook_uses_tool_name_matcher; test_agy_adapter.py::test_user_disabled_hook_stays_disabled

## RS-F13: User-only skills become model-invocable in Codex

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: skills/invocation
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: Codex ignores `disable-model-invocation`; its policy lives in agents/openai.yaml (skills/src/model.rs)
Action: _adapt_skill_dir writes agents/openai.yaml `allow_implicit_invocation: false` for disable-model-invocation skills and their sub-command skills
Verification: test_shared_outputs.py::test_user_only_skills_get_codex_policy

## RS-F14: Shared AGENTS.md commit template says "AI: Claude Opus 4.7"

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: portability/rule-content
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: common/rules/git-workflow.md:25 embedded for Codex/agy/Copilot
Action: Trailer is now `AI: <assisting model, e.g. Claude Opus 5.5 or gpt-5.5>`
Verification: test_shared_outputs.py::test_rendered_block_has_no_claude_provenance

## RS-F15: Missing jq makes every hook silently do nothing

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: robustness/hooks
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: A: PATH without jq → 'jq: command not found', exit 0, nothing formatted
Action: Helper prints a one-line `[Hook] jq not found` warning and exits 0 (agy still gets `{}`)
Verification: test_hooks.py::test_missing_jq_is_reported_not_silent

## RS-F16: Non-UTF-8 AGENTS.md crashes the run after other files are written

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: robustness/encoding
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: B: UTF-16 AGENTS.md → UnicodeDecodeError traceback, no manifest
Action: write_agents_md skips a non-UTF-8 AGENTS.md with a warning; marker reads use errors="replace"; .mcp.json/agy JSON decode errors leave files alone
Verification: test_shared_outputs.py::test_non_utf8_agents_md_left_alone

## RS-F17: Edited paths passed to tools without guarding leading '-'

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: robustness/args
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: B: patch paths flow straight into `ruff format <path>` etc.
Action: edited_files prefixes paths starting with '-' with './'
Verification: test_hooks.py::test_codex_patch_files_resolved_from_cwd (./-dash.py)

## RS-F18: Unknown-only --clis deploys Claude; README overstates agy read-only agents

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: docs/contract
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: A: `--clis codx` → CLAUDE.md + .claude/ created; README said read-only tool list though run_command is included
Action: cmd_init returns False and main exits 2 when no --clis id is known; README wording corrected
Verification: test_adapters.py::test_unknown_only_clis_is_an_error_not_claude

## RS-F19: Budget docstring claims the block always fits

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: contract/budget
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: A: budgets ≤1500 with all rules → 2321-byte pointer-only block
Action: write_agents_md warns when the block exceeds its budget even as pointers
Verification: test_shared_outputs.py::test_budget_floor_warns

## RS-F20: codex-cli/agy-cli pass prompts in argv (128 KiB per-argument cap)

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: robustness/argv
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: A: codex-cli canonical call put the prompt in argv; review diffs can exceed 128 KiB
Action: codex-cli pipes the prompt on stdin (verified live: `echo … | codex exec` → answer); agy-cli documents the limit and the --add-dir file workaround
Verification: doc contract; run_benchmark already sends Codex prompts on stdin (test_benchmark_backends.py)

## RS-F21: User handler in the foundry's Codex hook group → duplicates and dangling handlers

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: hooks/codex-reconcile
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: B: added ./scripts/my-lint.sh to the foundry group, deselected mypy → ruff twice, mypy-check.sh dangling (exit 127)
Action: Per-handler reconcile: foundry handlers removed wherever they are, empty groups dropped, user handlers kept
Verification: test_codex_adapter.py::test_user_handler_in_foundry_group_kept_without_dangling

## RS-F22: Legacy .github/skills removal has no ownership check

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: ownership/legacy
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: A: removes .github/skills/megamind-* by name only (matches old behavior)
Action: Removed only when its SKILL.md frontmatter names that skill
Verification: test_adapters.py::test_copilot_keeps_same_named_dir_that_isnt_the_foundry_skill

## RS-F23: Always-on set re-adds codex-cli/agy-cli on every update

Type: ACCEPTED_RISK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: skills/always-on
Status: OPEN
Owner: repo maintainer (approved 2026-09-24)
Trigger: any change to always-on semantics or a user complaint
Evidence: selection.py always_on; same documented semantics as copilot-cli/review-process
Action: Accepted: None — consistent with the documented always-on contract (README Skill Selection)
Verification: Re-check when the trigger fires

## RS-F24: --private on a non-Claude run is neither deployed nor saved to the manifest

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: lifecycle/private-sources
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or the hook/adapter contract of a target CLI changes
Evidence: orchestrator.py cmd_init — private sources are only returned by the Claude adapter; on a Codex/agy/Copilot-only run the report says "not deployed" and the manifest keeps only previously registered sources
Action: when no selected CLI deploys private sources, register --private sources in the manifest with all discovered content selected (the same selection the flag uses for Claude)
Verification: test_adapters.py::test_private_source_registered_on_non_claude_run

## RS-PN1: Absent review mode defaulted to AUDIT_ONLY although the user expected fix-after-triage

Type: PROCESS_NOTE
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: process/under-specified
Status: OPEN
Owner: not-assigned
Trigger: next review-process structural change
Evidence: User: "the t2 review process specifically states issues are to be fixed"; SKILL.md: "If the mode is absent, assume AUDIT_ONLY" vs Historical intent "triage and implement fixes across all severities"
Action: Ask for the mode in the same strategy prompt (or state the default explicitly in the review header prompt) so the user can pick FIX_AUTHORIZED up front
Verification: Next review-process edit resolves the contradiction between the mode default and the historical intent

## RS-PN2: Frame skill accepted without evidence it was applied

Type: PROCESS_NOTE
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: process/reviewer-routing
Status: OPEN
Owner: not-assigned
Trigger: next review-process structural change
Evidence: Pass-1 Reviewer B was told to apply megamind-adversarial; its report had no persona attack, pre-mortem, inversion or second-order sections, and the orchestrator accepted it
Action: Reviewer prompts must require the frame skill's steps as visible sections; the orchestrator checks them before accepting a report and records who applied which skill in the header
Verification: Every reviewer report in the re-review pass shows its skill's sections

## RS-PN3: Required review-output parts skipped

Type: PROCESS_NOTE
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: process/under-specified
Status: OPEN
Owner: not-assigned
Trigger: next review-process structural change
Evidence: Pass-1 output omitted the runtime detection step and printed a condensed table instead of the full ledger shape (Status, Prevention action, convergence, per-finding Evidence/Impact/guards)
Action: Record runtime profile in the header; write the full ledger (this directory) and summarise it in chat
Verification: This record's header and ledger

## RS-PN4: A reviewer finding was dropped between report and ledger

Type: PROCESS_NOTE
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2, 2026-09-24)
Tag: process/under-specified
Status: OPEN
Owner: not-assigned
Trigger: next review-process structural change
Evidence: A-13(d) (--private on non-Claude runs) was in Reviewer A's report but missing from the orchestrator's first-pass table
Action: Map every reviewer finding ID to a ledger ID (merged or separate) before presenting; recorded late as F24
Verification: Cross-check reviewer IDs against ledger IDs in every review

## RS-R1: Dropping a target stripped the Claude header through an AGENTS.md symlink

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: F5/F10 regression
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: Both: init claude,codex → ln -s CLAUDE.md AGENTS.md → init claude → header removed; next run skips the project and exits 0
Action: remove_agents_md never edits or deletes through a symlinked AGENTS.md; init exits 1 when it skips (R13)
Verification: test_shared_outputs.py::test_removal_never_edits_through_an_agents_md_symlink

## RS-R2: Catalog equality treated as MCP ownership: project-configured servers deleted

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: F9 regression
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: A: fresh project with memory/vercel from vendor docs → both removed on first init; B: hand-added firecrawl with real key removed on first upgrade, re-added railway removed every run
Action: Ownership requires a recorded name (manifest deployed_mcp; old manifests bootstrap from their mcp_servers) plus equality with the recorded/current rendering; identical selected entries are adopted; nothing else is removed
Verification: test_shared_outputs.py::test_first_run_never_removes_project_configured_servers, ::test_upgrade_bootstraps_ownership_from_previous_selection; test_agy_adapter.py::test_project_configured_catalog_server_is_never_removed

## RS-R3: Ruff gate fired on lint-only [tool.ruff.lint] and parent-directory configs

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: F1 incomplete
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: B: [tool.black] line-length=120 + [tool.ruff.lint] → file reformatted to 88 columns; parent pyproject above a black project → reformatted
Action: Ruff formats only with ruff.toml/.ruff.toml/[tool.ruff.format]/a ruff-format pre-commit hook and never with [tool.black]; has_config stops at the repository root
Verification: test_hooks.py::test_ruff_needs_a_format_signal_and_no_black[lint-only|black], ::test_config_above_the_repository_root_is_ignored

## RS-R4: Deselecting a server deleted an entry holding a real API key

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: F9 contract
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: A: firecrawl with a filled key, deselected → removed from .mcp.json and agy config
Action: Deselected owned entries with a filled placeholder are kept with a notice; README states the rule
Verification: test_agy_adapter.py::test_deselected_server_with_filled_key_is_kept

## RS-R5: A --clis typo undeploys a real target; drops need no confirmation

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: F10/F18
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: B: --clis claude,codx,agy → 'ignored: codx', Codex undeployed, manifest saved
Action: Any unknown id is an error (cmd_init False, main exit 2); interactive drops ask for confirmation (default no)
Verification: test_adapters.py::test_typo_among_valid_clis_never_drops_a_target, ::test_interactive_drop_needs_confirmation, ::test_main_exit_codes

## RS-R6: report() passed context in argv (E2BIG) with no size cap

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: F8
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: B: 80-file patch → 'jq: Argument list too long', rc 126; 20 files → 34,899 B of context
Action: Context piped to jq on stdin, capped at 8,000 characters with a truncation note
Verification: test_hooks.py::test_large_reports_are_capped_and_labelled

## RS-R7: Codex commandWindows contained cmd metacharacters

Type: DEFERRAL
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: F4/F11
Status: OPEN
Owner: not-assigned
Trigger: first Windows user report, or a Windows CI runner
Evidence: codex-rs command_runner.rs runs cmd.exe /C; `&&`/`||` sat outside double quotes
Action: Finder rewritten with if/then only (no & | < >); still relies on Git Bash parsing single quotes
Verification: test_codex_adapter.py::test_windows_command_has_no_cmd_metacharacters

## RS-R8: Nested-dirs finder test passed even when the finder ran nothing

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: tests/vacuous
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: A: mutant finder `exit 0` → test still green
Action: Test now asserts a stub ruff ran from the project and a nested cwd, and did not run elsewhere (path with ' and $)
Verification: test_codex_adapter.py::test_hook_command_finds_scripts_from_nested_dirs

## RS-R9: Codex finder could run a same-named script above the project

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: security/trust-boundary
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: codex.py finder walked to /
Action: Finder stops at the nearest directory with .codex/hooks.json
Verification: test_codex_adapter.py::test_finder_never_runs_a_script_above_the_project

## RS-R10: Default undeploy advised deleting .claude/ (manifest, VERSION)

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: lifecycle/advice
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: base.py undeploy message
Action: Claude-specific notice: keep .claude/setup-manifest.json and .claude/VERSION
Verification: test_adapters.py::test_claude_drop_notice_keeps_manifest_advice

## RS-R11: Minor leftovers (weak test param, empty dirs/{} file, decode error, stdout, long signature)

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: tests/cleanup
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: A: RA-8 (a)-(e)
Action: Guard test via monkeypatched render + header/inline param; empty .agents/skills and empty .mcp.json removed; UnicodeDecodeError caught; usage errors on stderr; deploy_shared_outputs takes the adapter lists
Verification: test_codex_adapter.py::test_invalid_merge_result_is_refused; test_shared_outputs.py::test_removing_all_shared_skills_removes_empty_root

## RS-R12: Check hooks pass pre-existing errors and repo-controlled text into agent context

Type: ACCEPTED_RISK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: F8/prompt-injection
Status: OPEN
Owner: repo maintainer (approved 2026-09-24)
Trigger: a report of hook context misleading an agent
Evidence: B: stub output with 'SYSTEM: ignore prior instructions…' passed verbatim
Action: Output labelled as tool diagnostics (not instructions) and capped; errors limited to the edited file's (not diff lines) — remaining risk accepted
Verification: test_hooks.py::test_large_reports_are_capped_and_labelled

## RS-R13: main ignored init failure (rc 0) so update-foundry never rolled back

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: cli/exit-codes
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: B: rc 0 on the RB-1 skip and on RB-4
Action: main exits 1 when init skips or aborts, 2 on usage errors
Verification: test_adapters.py::test_main_exit_codes

## RS-R14: Codex hook approvals invalidate when the handler strings change

Type: ACCEPTED_RISK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: hooks/approval-churn
Status: OPEN
Owner: repo maintainer (approved 2026-09-24)
Trigger: any change to _hook_handler strings
Evidence: Approval is stored by hash of the handler (command, statusMessage)
Action: Handler strings are now stable; changing them is a deliberate, release-noted act
Verification: Re-check when the trigger fires

## RS-PC1: Every write-path guard must also cover the removal path

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: architecture/ownership
Status: OPEN
Owner: not-assigned
Trigger: any new prune/undeploy/remove path
Evidence: R1 — the samefile guard existed in write_agents_md but not remove_agents_md
Action: Review checklist item for this repo: for each new deletion path, list the write-path guards and show the same guard (or a stricter one) applies
Verification: test_shared_outputs.py::test_removal_never_edits_through_an_agents_md_symlink

## RS-PC2: Ownership proofs must come from a record the foundry wrote

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 1)
Tag: architecture/ownership
Status: OPEN
Owner: not-assigned
Trigger: any new artifact type the foundry prunes
Evidence: R2 — content equality with the catalog deleted project-configured MCP servers
Action: Accept as ownership proof only a marker the foundry wrote into the artifact, a foundry-namespaced location, or a record in the manifest — never content equality alone
Verification: test_shared_outputs.py::test_first_run_never_removes_project_configured_servers

## RS-R2-1: Empty MCP ownership record not saved; next run treats the manifest as pre-upgrade

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 2)
Tag: F9/R2 incomplete
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: A: Codex-only run → no deployed_mcp; later run bootstraps from mcp_servers and removes the project's identical memory, deleting .mcp.json; B: early return left a stale None record
Action: deployed_mcp always written (even {}); write_mcp_servers clears the record on its early return; _mcp_state ignores malformed fields
Verification: test_adapters.py::test_ownership_record_saved_even_when_empty, ::test_malformed_manifest_mcp_fields_dont_crash; test_shared_outputs.py::test_missing_mcp_json_clears_the_record

## RS-R2-2: A project's empty .mcp.json / .agents/mcp_config.json / hooks.json deleted

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 2)
Tag: regression/data-loss
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: B: master project with committed {"mcpServers": {}} (what `claude mcp remove --scope project` leaves) → D .mcp.json after one run; agy {} likewise
Action: Files are rewritten only when the reconcile changed them, and deleted only when the foundry removed its entries and nothing else remained (.mcp.json, agy mcp_config.json and hooks.json, Codex hooks.json)
Verification: test_shared_outputs.py::test_projects_empty_mcp_json_survives[{}|{"mcpServers": {}}]; test_agy_adapter.py::test_projects_empty_config_files_survive; test_codex_adapter.py::test_projects_empty_hooks_json_survives

## RS-R2-3: Codex managed block dropped a filled-in key on deselect/undeploy

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 2)
Tag: F9 contract
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: A: key filled → kept when reselected, lost after deselect, no notice
Action: A deselected server with a filled placeholder moves out of the foundry block into the project's part of config.toml, with a notice
Verification: test_codex_adapter.py::test_deselected_server_with_filled_key_moves_out_of_block

## RS-R2-4: Ruff gate still accepted a lint-only ruff.toml and missed black via pre-commit

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 2)
Tag: F1/R3 incomplete
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: B: ruff.toml [lint] only → formatted; ruff.toml + pre-commit `id: black` → formatted; comment mentioning ruff-format → formatted
Action: ruff.toml/.ruff.toml need a [format] section or format. key; pre-commit matched by `id: ruff-format`; black detected in pyproject or as a pre-commit hook id
Verification: test_hooks.py::test_ruff_needs_a_format_signal_and_no_black (8 cases), ::test_config_at_the_repository_root_still_counts

## RS-R2-5: README said catalog-matching project entries are never touched, but selecting adopts them

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 2)
Tag: docs/contract
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: A: project's own memory selected then deselected → removed (adopted)
Action: README states the adoption rule
Verification: README Upgrading section

## RS-R2-6: Removal guards: hard-linked AGENTS.md, symlinked .agents/skills

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 2)
Tag: robustness/links
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: A: hard link AGENTS.md↔CLAUDE.md bypasses the is_symlink guard; B: .agents/skills → empty dir symlink → NotADirectoryError
Action: remove_agents_md also checks samefile(CLAUDE.md); remove_shared_skills leaves a symlinked root alone
Verification: test_shared_outputs.py::test_removal_skips_a_hard_linked_agents_md, ::test_symlinked_skills_root_left_alone

## RS-R2-7: Skip/decline reported as "ERROR … failed" by update-foundry

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 2)
Tag: cli/exit-codes
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: B: stubbed update → skip → rc 1 and "ERROR: setup.py init failed"
Action: setup.py init exits 3 when nothing is applied by design; update-foundry.sh prints "Update not applied … keeping the previous version" for 3, the error text otherwise
Verification: test_adapters.py::test_main_exit_codes

## RS-R2-8: Declined drop silently keeps the target

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 2)
Tag: ux
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: B: --clis claude, Enter at the drop prompt → Codex kept, no message
Action: Prints "Keeping <name> as a target."
Verification: test_adapters.py::test_interactive_drop_needs_confirmation

## RS-R2-9: Test gaps: Windows ^/% not checked, repo-root config honoured, finder rc

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 2)
Tag: tests/quality
Status: RESOLVED
Owner: not-assigned
Trigger: the guard test fails, or a target CLI's contract changes
Evidence: A: listed gaps
Action: Windows metacharacter test covers & | < > ^ %; repo-root config test; finder test asserts rc 0
Verification: test_codex_adapter.py::test_windows_command_has_no_cmd_metacharacters, ::test_finder_never_runs_a_script_above_the_project; test_hooks.py::test_config_at_the_repository_root_still_counts

## RS-R2-10: Nested .codex/hooks.json between cwd and project makes the hook a no-op; UTF-8 cut under LC_ALL=C

Type: ACCEPTED_RISK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 2)
Tag: hooks/edge
Status: OPEN
Owner: repo maintainer (approved 2026-09-24)
Trigger: a report of a hook not running in a nested layout
Evidence: A: finder stops at the nearest hooks.json; C locale caps by bytes (JSON stays valid)
Action: Accepted: stopping at the nearest project boundary is the safer trust rule (R9); cosmetic byte cut
Verification: Re-check when the trigger fires

## RS-R2-11: Interactive CLAUDE.md Quit happens after Claude files were written (pre-existing)

Type: ACCEPTED_RISK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 2)
Tag: ux/ordering
Status: OPEN
Owner: repo maintainer (approved 2026-09-24)
Trigger: next change to the Claude adapter's CLAUDE.md flow
Evidence: claude.py R/M/Q prompt comes after the rules/skills/settings writes (same on master)
Action: Accepted: pre-existing ordering, self-heals; moving the prompt is a separate Claude-adapter change
Verification: Re-check when the trigger fires

## RS-PC3: A project file the foundry didn't change is never rewritten or deleted

Type: CONVERTED_CHECK
Source review: docs/review-state/T2-2026-09-24-multi-cli.md (T2 re-review pass 2)
Tag: architecture/ownership
Status: OPEN
Owner: not-assigned
Trigger: any new config writer
Evidence: R2-2 — empty project files deleted because "empty after reconcile" was taken to mean "held only foundry entries"
Action: Writers compare against the original content: no change → no write; delete only after removing the foundry's own entries left nothing else
Verification: test_shared_outputs.py::test_projects_empty_mcp_json_survives; test_agy_adapter.py::test_projects_empty_config_files_survive
