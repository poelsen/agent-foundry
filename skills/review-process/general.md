# General Review Process

Use this process for non-software work: decisions, plans, documents,
operations, design tradeoffs, communication, policy, and any artifact where
evidence and judgment matter but code-specific checks do not apply.

This process extends the canonical rules in [SKILL.md](SKILL.md).

## Goal

The review should answer four questions:

1. Is the conclusion supported by evidence?
2. What could go wrong if we act on it?
3. What tradeoffs or alternatives were ignored?
4. What decision should be made now, deferred, accepted, or rejected?

## General flow

1. Declare review mode, risk tier, model strategy, budget, and scope.
2. List assumptions as verified, inferred, or uncertain.
3. Select reviewers from the canonical routing table.
4. Review evidence and separate observations from interpretation.
5. Explore alternatives for T2+ reviews.
6. Triage findings with the shared ledger.
7. Decide and close using the shared completion criteria.

## General checklist

- [ ] Scope is explicit: what is in, out, and deferred.
- [ ] Success criteria are visible.
- [ ] Assumptions are listed and critical assumptions are verified where cheap.
- [ ] Evidence is cited or uncertainty is labeled.
- [ ] Alternatives were considered, not only mentioned.
- [ ] Failure modes and second-order effects were explored.
- [ ] Reversibility and rollback are understood.
- [ ] Stakeholders or affected users are named where relevant.
- [ ] Cost, compliance, schedule, or reputation risks are called out when they
      apply.
- [ ] Model choice matches the risk/cost tradeoff, or user-specified models
      were followed and verified.
- [ ] Decision outcome is explicit: do, do not do, defer, accept risk, or
      experiment.
- [ ] Related review-state entries were searched, or "no prior data available"
      was recorded.

## Documentation review appendix

Apply this appendix to docs, policies, and process files.

- [ ] Entry point is obvious.
- [ ] Cross-links resolve and point to the canonical source.
- [ ] Terms are used consistently across files.
- [ ] Shared concepts are defined once and linked elsewhere.
- [ ] Examples match the rules they illustrate.
- [ ] The document says what to do for both normal and edge cases.
- [ ] The document defines stop conditions, not only start conditions.
- [ ] The document distinguishes facts, decisions, and guidance.
- [ ] Navigation supports the expected reader path.
- [ ] Repeated findings from prior doc reviews are represented in review-state.

## Process self-review triggers

Run a T4 review of the review-process family when:

- a new process layer or concern module is added;
- a major finding was missed by the existing process;
- review cost repeatedly exceeds the risk of the work;
- model selection repeatedly produces weak, duplicated, or overpriced review
  coverage;
- reviewer routing or model/tool evidence proves unreliable;
- recurring findings appear without conversion into checks.

## Output addendum

General reviews should include a decision block:

```text
Decision: <do | do not do | defer | accept risk | experiment>
Decision rationale: <evidence-based rationale>
Open risks: <remaining risks and owners>
```
