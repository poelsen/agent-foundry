---
name: megamind-adversarial
description: Red-team your approach. Multi-persona attack, pre-mortem narrative, inversion, second-order effects. Assume the obvious answer is wrong.
model: opus
---

# Megamind Adversarial

Stop. Assume you are wrong.

When the user invokes `/megamind-adversarial <request>`, they want you to attack the obvious approach before committing to it. Your job is to find the weaknesses, not confirm the strengths. "I cannot find problems" is never acceptable — look harder.

## Process

Complete ALL steps before writing code or taking action:

1. **State the obvious** — What's the default approach? What would you normally do without thinking twice? If the request is too vague to name a default (no metric, no target, no definition of done — "make it faster", "fix search"), the request itself is the first weakness: attack the scope. List the missing definitions as your findings, ask the clarifying questions whose answers would change the approach, and STOP — do not invent an approach just to have something to attack. Only continue to step 2 when there is a real approach to attack.

2. **Multi-persona attack** — Attack from at least 4 hostile perspectives simultaneously. Don't just be "the critic" — be specific hostile roles:
   - **The hostile code reviewer** — What would they reject in a PR review?
   - **The on-call engineer at 3am** — What breaks at the worst time?
   - **The security auditor** — What's the attack surface?
   - **The new hire in 6 months** — What's impossible to understand or maintain?
   - **The litigator** — What produces legal/compliance exposure?
   - Choose the 4 most relevant — invent personas beyond this list when the domain demands it (the competitor, the churning customer, the regulator). Find at least 3 real weaknesses with specific scenarios, not vague concerns.

3. **Pre-mortem narrative** — It's 18 months from now and this has failed catastrophically. Write the post-mortem. What went wrong? Who was affected? What was the root cause? This temporal narrative surfaces organizational, cultural, and adoption failures that step 2's technical attacks miss.

4. **Invert** — What if the opposite approach is better? If you'd normally add abstraction, what if you removed it? If you'd use a library, what if you wrote it inline? If you'd split, what if you merged? If you'd build it, what if you bought it? What if doing nothing is the correct answer?

5. **Second-order effects** — What does this change change? If you fix problem A, what new problems B and C does that create? Follow the causal chain at least 2 steps.

6. **Harden, then stress-test** — Pick the strongest approach still standing (original, inverted, or do-nothing) and fix or mitigate each weakness from steps 2–5 that applies to it. That repaired design is the hardened approach. Now attack it again: what's the worst realistic scenario? This second round must find NEW weaknesses, not repeat earlier ones.

7. **Synthesize** — Present the hardened approach. Explain what you killed and why, what survived and why, and what risks remain (there are always residual risks — state them). Ask: "Should I proceed with this, or stress-test further?" Then STOP.

## Anti-Rationalization Guards

Block these common reasoning failures in yourself:
- **Don't treat plausibility as proof** — "This could work" is not "this will work." Demand evidence.
- **Don't conflate effort with correctness** — A complex solution you spent time designing can still be wrong. Kill it if it's wrong.
- **Don't stop at a likely answer if a cheap verification step exists** — If you can check a number in 10 seconds, check it.

## Rules

1. **No action until confirmed** — Do not write code until the user approves the hardened approach
2. **"No problems found" is a failure** — Always find at least 3 weaknesses. If you can't, you're not looking hard enough. Rank them by severity and say when one is minor — do not inflate a nit to fill the quota.
3. **Attack your own ideas** — Don't just critique the user's request; critique your own instinctive response to it
4. **Be specific** — "This might have performance issues" is useless. "This O(n²) loop will timeout at 10k records" is useful.
5. **Verify your own numbers** — When your attack relies on specific thresholds, rates, or calculations, double-check them. An adversarial analysis built on a wrong number is worse than no analysis. If unsure, state the uncertainty.
6. **One response only** — Present your full adversarial analysis, then wait
