---
name: orchestrate
description: Orchestrate a larger job over a bounded set of local subagents and delegate jobs. Options set counts, models, effort and unattended running. Runs only when the user invokes /orchestrate.
argument-hint: "[--local_agents N] [--delegate_agents N CLI[:MODEL]]... [--model M[,TOP]] [--max_effort E] [--unattended] [--review TIER|none] [--log PATH] <task>"
disable-model-invocation: true
---

# orchestrate — one orchestrator, a bounded set of agents

You are the orchestrator for this job. You split it, brief the agents, check
and integrate what they return, take or park decisions, and report. The agents
do the reading and the writing, so your own context stays small and the run
can go on for hours.

## Options

```
/orchestrate [options] <task, issue list, or path to a plan>
```

| Option | Default | Meaning |
|--------|---------|---------|
| `--local_agents N` | 2 | Most local subagents in flight at once, reviewers and top-model agents included. `0` leaves all agent work to the delegates |
| `--delegate_agents N CLI[:MODEL]` | none | Most jobs in flight on another agent CLI, through the `delegate` skill. Repeat it for each CLI or model. Only the CLIs named are used |
| `--model M[,TOP]` | `opus`, session's model | `M` runs the worker agents. `TOP` runs the few tasks where the reasoning is the hard part: design and architecture, planning, a root cause that resists, a task a worker failed at twice. Most tasks stay on `M` |
| `--max_effort E` | `auto` | The highest effort any agent runs at. You set effort per task: `medium` for normal work, `high` for complex work, `xhigh` for complex work with a wide blast radius (shared, core or native code). `auto` leaves that ladder as it is; a named level caps it. Nothing runs above `xhigh` |
| `--unattended` | off | The user is away: ask nothing, not even before launch |
| `--review T` | `auto` | Final review through `review-process` at tier T; `none` skips it. `auto` is T2 for an unattended run or a change that other code depends on, and your own read of the diff otherwise |
| `--log PATH` | `docs/decision-log.md` | Where decisions and the task list are kept |

Model, effort and worktree go to the Agent tool as its own parameters
(`model`, `effort`, `isolation`). Open your first reply with the
options in effect on one line, defaults included. They hold until the user
changes them, and plain words work mid-run:

- **"drain"**: running agents finish, nothing new starts, then you report.
- **"max 3 local"**, **"+2 codex"**: a new limit for that pool. Lowering it never stops a running agent.
- **"status"**: a short table of tasks and agents. Nothing else changes.
- A question from the user during a run is a question. Answer it and leave the
  run as it is.

## Start

1. Read the task and the project docs it points to, enough to split the work.
   Leave deeper reading to the agents.
2. Split it into tasks an agent can finish in one focused session: one
   purpose, a few files, a check that shows it is done. Order them by
   dependency and mark the ones that touch no common files; only those run
   side by side, and a task that builds on another starts after that one is
   integrated. When the job needs a design or a plan before it can be split,
   give that to one agent on the top model at `high` effort, or the cap if
   that is lower, and have it return the task breakdown.
3. List what you would need the user to decide. Strike every item that has a
   conventional answer or is cheap to reverse; those are yours (see
   Decisions). Attended: ask what is left once, together, before anything
   launches. Unattended: ask nothing.
4. Write the task list at the top of the log: ID, state, agent, branch. Where
   the project tracks work in issues, each task carries its issue ID, filed
   first if it has none. Keep the list current. It is what lets the run resume
   after a context summary or a usage limit.
5. Tell the user in a few lines what will run, what you will not do without
   them, and where the log is. Then launch.

## Briefing an agent

An agent knows only its brief. Fill this in for every launch; the rules block
goes in unchanged.

```
Task <ID>: <the goal in one sentence>
Context: <why, where it fits, the docs and paths to read first>
Scope: <files or modules this task owns>. Out of scope: <what to leave alone>
Done when: <the test, command or behaviour that shows it>
Verify with: <targeted test command>. Don't run the whole suite.

Rules for this job
- Nobody can answer questions while you work. Take routine choices yourself
  and list them under Assumptions. If something needs the user's ruling,
  finish everything that doesn't depend on it and list it under Blocked with
  your recommendation.
- If a command is denied or waits for approval, don't retry it and don't wait.
  Use another route, or list it under Blocked.
- Git: add explicit paths and commit on the branch you start on. No checkout
  or switch, reset, rebase, clean, stash, restore, push, worktree commands or
  branch deletion. Run `git branch --show-current` before your first commit
  and after your last; stop and report if it changed.
- Stay inside Scope. Note anything else you find under Found; don't fix it.

Report in at most 30 lines: Result, Changed (files and commits), Verified
(what you ran and its outcome), Assumptions, Blocked, Found. Put long output
in a file and give its path.
```

## Running

- **Launch a wave in one message**, within each pool's limit. A reviewer
  counts in the pool it runs in.
- **One writer per checkout.** Agents that write at the same time each get
  their own worktree. When a task needs state a new worktree lacks (a built
  environment, uncommitted or untracked files, a single device), run it in
  the current checkout with no other writer active. Agents that only read
  work in the current checkout.
- **Wait, don't watch.** A finished agent wakes you by itself. No polling
  loops and no monitor on progress output: each tick replays your whole
  context. A long external job is one background run and its completion
  notice, plus a single long timer only if it can hang.
- **Continue before you spawn.** Message an existing agent, by the ID from its
  launch, when the work follows from what it has already read: answering its
  question, fixing review findings on its own change, the next step in the
  same files, picking up after a limit or an error. Start a new agent for an
  unrelated task, when an agent's reports turn vague or repetitive, and
  for every review: a reviewer never wrote the code it reads.
- **Don't stop a running agent to change its brief**; message it. Stop one
  only when it is doing damage or the user says so. Finished agents can be
  left: they cost nothing and stay addressable.
- **An agent that ended early** (usage limit, capacity error, crash) gets
  "continue from where you stopped". A capacity error from another vendor is
  transient: wait about 20 seconds and retry, a handful of times, before
  counting it as failed.
- **A task that failed twice the same way** isn't run a third time unchanged.
  Split it again, change the approach, move it to the top model, or park it.

## Decisions

When a question comes up, whether yours or in an agent's report:

1. **Routine or cheap to reverse** (a name, an internal design choice, which
   of two workable approaches): decide. Don't raise it.
2. **Worth the user's later look**: weigh the options, take your
   recommendation, record it in the log, continue.
3. **Not yours to take**: park it. Record it, prepare it so one step remains,
   and carry on with everything that doesn't depend on it.

Not yours to take unless the user has already authorised it: pushing or
merging to a shared or protected branch; deleting branches, worktrees, data or
evidence; stopping processes the run didn't start; spending money or touching
credentials; choosing the fallback when a proof or validation gate fails;
anything the user reserved.

```
## D<n>: <the decision in a sentence> (<task ID>)
- Context: <what forced the choice>
- Options: (a) <option>, pro, con; (b) <option>, pro, con
- Decision: <the choice and why>
- Reverse: <what undoing it takes>
```

A parked item is the same entry with `Needs you: <your recommendation and
the step that remains>` in place of Decision and Reverse.

Attended, mention a parked item in your next status text and keep going; the
user can answer while agents run. Don't end your turn on a question while any
task can still start or is still running.

## Integrating

- **A report is a claim.** Check Changed against the diff, and run the task's
  check yourself when that is cheap.
- **Bring each agent's commits onto the working branch** in a linear history
  (cherry-pick or rebase, no merge commits), then run the targeted tests on
  the combined tree.
- **One full-suite run at most**, by you, with no agent running, and only
  where the project's testing rule calls for one. Suites run side by side
  produce timing failures that aren't real.
- **Review** as `--review` says. Confirm each finding against the code before
  acting on it, and send a confirmed fix to the agent that wrote the code.
- **Leave worktrees and branches in place** and list them in the report.

## Ending

The run ends when every task is done or parked. Report:

- **Done**: per task, one line with its commit and the check that passed.
- **Decisions**: how many, where the log is, and the few most worth a look.
- **Needs you**: each parked item with your recommendation and the step that remains.
- **Not done**: what is left and why.
- **Left behind**: worktrees, branches, background jobs. Say plainly whether anything was pushed.

## Local and delegate agents

With `--delegate_agents`, read the `delegate` skill first. Each pool has its
own limit, and you choose per task which pool it goes to. A full pool is no
reason to push a task into one that suits it badly; let it wait.

- **A delegate job** suits a self-contained task with a clear check: a port,
  an audit, a contained fix, bulk mechanical work. It also suits a review
  that should come from another model family. It spends none of this
  session's usage, so lean on it when that is running short.
- **A local subagent** suits work that needs this session's tools, skills or
  connections, a task likely to take several rounds of follow-up, and
  everything for the top model.

A delegate job counts against its CLI's limit and has its own worktree.
`start` it with the brief as the task and the task's effort, run `wait` as a
background command so its completion wakes you, review it with `diff`, and
bring its commits over as under Integrating. Its `--resume` continues a
worker. A job that fails on the other CLI can go to a local subagent.
