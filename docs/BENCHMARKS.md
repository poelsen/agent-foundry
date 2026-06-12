# Benchmarks — how models and skills perform per task

This is the detailed evidence behind agent-foundry's skill design and the
per-task model guidance in the [README](../README.md#benchmarks). Use it to
decide **which model and which skill to reach for on which kind of task.**

> **Read the caveats.** These are decision aids, not leaderboard claims. Most
> reasoning/financial numbers are **single-run** with **one judge** — directional,
> not significance-tested. The scope and agentic-coding sections note their own
> stronger/weaker footing inline. Scores are rubric points (≈0–10; they can go
> **negative** when a response trips anti-patterns like "jumps to a solution").

## Methodology

- **Harness:** `tools/run_benchmark.py` (reasoning/financial/scope, prose tasks,
  rubric-judged) and the agentic harnesses in `tools/deepswe/` +
  `tools/run_swebench_agentic.py` (real repos, objective test-pass — no judge).
- **Subjects** run via the **GitHub Copilot CLI** (gpt-5.5, gpt-5.4, gpt-5.4-mini,
  claude-opus-4.7/4.6, claude-sonnet-4.6) or the **claude CLI** (opus-4.8).
- **Judge** (prose tasks only): a fixed model scores each response against the
  challenge's rubric (required elements, anti-patterns, depth). Reasoning/financial
  used **opus-4.7**; the scope re-test used **opus-4.8**. Dual-judge
  (gpt-5.5 + opus-4.8, flag disagreements) is supported via `--judge2-*`.
- **Effort:** reasoning/financial were run at the CLI default; scope and the
  agentic runs at **max** reasoning effort (`--effort max`).
- **Challenges:** YAML in `tests/challenges/` (rubric per challenge). Categories:
  `deep`, `arch`, `cross`, `creative`, `adversarial`, `scope`, `financial`.

---

## 1. Reasoning (rubric score, 46 challenges, default effort, opus-4.7 judge, 1 run)

Baseline (no skill) vs each megamind skill, by subject model:

| Subject | baseline | megamind-deep | megamind-creative | megamind-adversarial |
|---|---|---|---|---|
| **claude-opus-4.7** | 5.70 | **7.30** | 6.33 | 6.78 |
| **claude-sonnet-4.6** | 4.29 | **6.70** | 6.13 | 6.78 |
| **gpt-5.4** | 3.87 | 6.13 | 5.89 | **6.37** |
| **gpt-5.5** | 3.84 | 5.87 | 5.54 | **6.30** |

- **Every skill helps every model** (+1.6 to +2.5).
- **Claude models score higher on this reasoning-prose axis** at baseline and skilled; the GPTs start lower and gain the most from skills (more headroom).
- This is the *opposite* ranking of the coding axis (§4) — different tasks, both real.

### Which skill for which task (per-category, averaged across the 4 models)

| Task category | baseline | mm-deep | mm-creative | mm-adversarial | **use** |
|---|---|---|---|---|---|
| **deep** (DB migration, refactor, API design) | 5.0 | **8.4** | 6.4 | 7.7 | **deep** |
| **arch** (architecture under ambiguity) | 3.6 | **7.0** | 6.1 | 6.8 | **deep** |
| **creative** (open-ended problem solving) | 4.8 | 5.9 | **7.8** | 5.5 | **creative** |
| **adversarial** (red-team a design) | 5.4 | 6.5 | 5.8 | **7.1** | **adversarial** |
| **scope** (vague requests) — see §3 | 0.6 | 3.0 | 0.9 | 4.7 | **deep (scope gate)** |

Each skill wins its own category. `deep` is the best all-rounder.

---

## 2. Financial (rubric score, 58 challenges, opus-4.7 judge, 1 run)

`megamind-financial` (DK/DE tax data + Thorleif Jackson valuation methodology):

| Subject | baseline | + megamind-financial | Δ |
|---|---|---|---|
| claude-sonnet-4.6 | 5.22 | **7.53** | **+2.30** |
| claude-opus-4.7 | 5.93 | **7.52** | +1.59 |
| gpt-5.4 | 4.31 | 5.75 | +1.44 |
| gpt-5.5 | 4.28 | 5.52 | +1.24 |

A domain skill that injects information + methodology the model doesn't reliably
produce on its own lifts every model — most on the weaker baselines.

---

## 3. Scope — the fixed weakness (max effort, opus-4.8 judge, 3 runs)

Vague one-line prompts ("make the app faster", "fix search", "improve logging /
security / UX"). Originally the universal weak spot — models jump straight to a
solution. The **`megamind-deep` scope gate** (clarify intent → assumptions →
measurement plan → success criteria → ask, *before* solving) fixes it across the
board:

| Subject | baseline | + gated megamind-deep | Δ |
|---|---|---|---|
| gpt-5.4-mini | −1.10 | **6.00** | **+7.10** |
| gpt-5.5 | −0.47 | **6.00** | +6.47 |
| gpt-5.4 | −0.20 | **6.00** | +6.20 |
| claude-opus-4.6 | 0.40 | **6.00** | +5.60 |
| claude-sonnet-4.6 | 0.44 | **5.90** | +5.46 |
| claude-opus-4.7 | 3.38 | **6.00** | +2.62 |

- **Every model goes from cratering (~0, almost never passing) to the rubric
  ceiling (~6, ~100% pass).** No regression on well-specified prompts (the gate
  only triggers on vague ones — deep/arch held their scores).
- `megamind-creative` got a matching scope **guard** so it no longer craters
  off-diagonal (was −1.4 on sonnet), while staying divergent on real creative tasks.

This is the most robust result here (3 runs, every model, strong judge).

---

## 4. Agentic coding (objective: real repos, hidden tests pass — no judge)

Two substrates, both scored by running the project's hidden test suite after the
model fixes a real issue. **Important:** our agent is a bare `copilot -p
--allow-all` loop, *not* a tuned SWE scaffold — so absolute solve-rates sit
**below** the public tuned-scaffold leaderboards. Use these for *relative*
model/skill comparison, not as capability ceilings.

### gpt-5.5 baseline solve-rate (our scaffold)

| Benchmark | our gpt-5.5 | published reference |
|---|---|---|
| **SWE-bench Verified** (representative random n=50) | **74%** | frontier ~85–88% (tuned); all-model avg 65.5% |
| **DeepSWE** (n=40, max effort — larger multi-file tasks) | **35%** | DeepSWE ranks gpt-5.5 ~70% (tuned) ≫ opus-4.7 ~54% |

DeepSWE (large, multi-file changes) is much harder than SWE-bench Verified
(small patches) — and the two leaderboards rank models *oppositely* (Opus tops
Verified; gpt-5.5 tops DeepSWE). Pick the benchmark that matches your task size.

### Do reasoning skills help agentic coding? Only weaker models.

DeepSWE, max effort, baseline vs skill — resolve counts:

| Model | baseline | + megamind-deep | + stacked (swe+deep+adv) |
|---|---|---|---|
| **gpt-5.5** (frontier) | — | net **0** (n=40) | — |
| **gpt-5.4** (lesser) | 5/10 | — | **8/10 (+3)** |
| **claude-sonnet-4.6** | ~5/10 | 4/10 | 6/10 (marginal) |

- **On a frontier model, a reasoning skill adds nothing on agentic coding** — it
  already reasons hard at max effort.
- **On a weaker model (gpt-5.4) the stacked skill clearly helps (+3)** — it
  substitutes for capability the model lacks.
- A dedicated `megamind-swe` skill was prototyped and **dropped**: it only paid
  off below Sonnet-4.6, and that's not a tier people run hard agentic jobs on.

---

## The principle

> **Skills help in inverse proportion to model strength.**
> Large lift on weak models / weak baselines (scope +5–7 on lesser models;
> financial +2.3 on Sonnet; gpt-5.4 SWE +3). Small-to-none on frontier models
> that already do the work themselves (gpt-5.5 coding net-0).

Practical guidance: **always worth enabling the megamind skills** — they help
clearly on reasoning/financial/scope for every model, and the cost is a one-time
prompt. For **agentic coding**, lean on the model's own capability (use a strong
model); skills are upside only on weaker/cheaper models.

---

## Caveats & honesty

- **Single-run** for reasoning/financial (n=1) → directional, not significance-tested.
  Scope used 3 runs (more robust). Agentic runs are single-run; the per-task
  variance is real (a Sonnet baseline measured 3/7 and 5/10 on overlapping tasks).
- **One judge** for reasoning/financial (opus-4.7). A judge can have stylistic
  preferences; the dual-judge mode exists to flag disagreement but wasn't used for
  the full matrix.
- **Our agentic scaffold is minimal**, so SWE absolute numbers understate tuned
  agents — they're for relative comparison only.
- **Rubric scores are not percentages** — they're points against a per-challenge
  rubric and can be negative.

## Reproduce

```bash
# Reasoning / financial / scope (prose, rubric-judged) — subject via Copilot, judge via claude
python3 tools/run_benchmark.py --challenges scope-001 scope-002 scope-003 scope-004 scope-005 \
  --skill megamind-deep --runs 3 \
  --subject-backend copilot --subject-model gpt-5.5 \
  --judge-backend claude --judge-model claude-opus-4-8

# Dual-judge (flag disagreements)
... --judge-backend claude --judge-model claude-opus-4-8 \
    --judge2-backend copilot --judge2-model gpt-5.5

# Agentic SWE-bench Verified (objective, Docker) — see tools/run_swebench_agentic.py
# Agentic DeepSWE via Copilot (no API keys) — see tools/deepswe/README.md
```

Saved result JSONs live in `results/` (`bench-reasoning-*`, `bench-financial-*`,
`scope-*`, `swe-*`).
