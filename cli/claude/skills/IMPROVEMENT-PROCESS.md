# Megamind Skill Improvement Process

Repeatable process for iterating on megamind skills. Follow these steps exactly.

## When to Run

- After modifying any skill SKILL.md
- After adding new challenges
- Before releasing a new version
- Quarterly maintenance (update DK tax data, verify rubric alignment)

## Prerequisites

- `claude` CLI authenticated and in PATH
- `uv run pytest` passes
- Working directory: `claude-foundry/`

## Step 1: Update Tax Data (if DK financial, annual in January)

```bash
# Copy previous year and update
cp skills/megamind-financial/data/dk-tax-2025.md skills/megamind-financial/data/dk-tax-2026.md
# Edit the new file with current year's rates from skat.dk
# Update the skill SKILL.md if structural rules changed
```

## Step 2: Run Full Regression Suite

```bash
# Verify all tests pass
uv run pytest --no-cov

# Run the automated benchmark (from terminal, not inside Claude Code)
python3 tools/run_benchmark.py --skill megamind-deep --runs 2 --save results/deep-v$(date +%Y%m%d).json
python3 tools/run_benchmark.py --skill megamind-adversarial --runs 2 --save results/adversarial-v$(date +%Y%m%d).json
python3 tools/run_benchmark.py --skill megamind-creative --runs 2 --save results/creative-v$(date +%Y%m%d).json
python3 tools/run_benchmark.py --skill megamind-financial --runs 2 --save results/financial-v$(date +%Y%m%d).json

# Compare against previous baseline
python3 tools/run_benchmark.py --skill megamind-deep --runs 2 --compare results/deep-vPREVIOUS.json
```

## Step 3: Identify Weaknesses (In Claude Code Session)

```
/megamind-adversarial Red-team the benchmark results. Which challenges show
the smallest skill-vs-baseline delta? Which depth elements score lowest?
Where is the skill NOT adding value over baseline?
```

## Step 4: Generate Improvement Hypotheses

For each weakness found:
1. Is the rubric testing the right thing? (If not, fix the rubric)
2. Is the skill missing a technique? (If so, add it)
3. Is the skill's instruction unclear? (If so, sharpen it)
4. Is this a domain knowledge gap? (If so, add to data files)

## Step 5: Implement Changes

Edit the skill SKILL.md. Follow these rules:
- **Don't add process steps that baseline already does** — only add steps that produce structurally different output
- **Don't make the skill longer just to be thorough** — every line must earn its place
- **Test the change on the weakest challenge first** — if it doesn't help there, it's not the right fix

## Step 6: Verify No Regressions

```bash
# Run the full suite again
python3 tools/run_benchmark.py --skill [modified-skill] --runs 2 --save results/[skill]-v[date]-post.json
python3 tools/run_benchmark.py --skill [modified-skill] --runs 2 --compare results/[skill]-v[date]-pre.json
```

Check:
- [ ] No challenge that previously passed now fails
- [ ] The weakest challenges improved (or at least didn't regress)
- [ ] Depth scores on modified elements are stable or improved

## Step 7: Run Cross-Skill Tournament (Optional, for major changes)

Test the modified skill on OTHER skills' domain challenges to verify it hasn't become domain-specific:

```
# In Claude Code session, launch agents:
# - Modified skill on its own domain (should win)
# - Modified skill on another domain (should not hurt)
# - Other skills on modified skill's domain (verify it still wins)
```

## Step 8: Adversarial Review

```
/megamind-adversarial Red-team the changes made in this iteration.
Are the improvements real or measurement artifacts? Did we make the
skill longer without making it better? Would a hostile reviewer approve?
```

## Step 9: Commit and Document

```bash
git add skills/ tests/challenges/ tools/
git commit -m "feat/fix: [description of skill changes]

Benchmark results: [before] -> [after] on [which challenges]
Regression check: [pass/fail]

AI: Claude Opus 4.7"
```

## Annual DK Tax Data Maintenance

Every January:
1. Check skat.dk for updated rates and thresholds
2. Create `data/dk-tax-YYYY.md` from the template
3. Verify: aktieindkomst brackets, topskat threshold, pension limits, ASK limit, PAL-skat rate
4. Run financial challenges to verify the skill uses updated data
5. Commit with message: `chore: Update DK tax data for YYYY`

## Challenge Maintenance

Every 6 months:
1. Run `/megamind-adversarial` on the challenge suite itself — are rubrics still aligned with skills?
2. Check if any challenges have become trivially easy (baseline scores 100%) — retire or harden them
3. Add 2-3 new challenges per skill targeting newly identified weaknesses
4. Verify total challenge count and depth coverage: `grep -l "depth_elements" tests/challenges/*.yaml | wc -l`
