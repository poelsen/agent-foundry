# DeepSWE via Copilot CLI (no API keys)

Run the [DeepSWE](https://github.com/datacurve-ai/deep-swe) benchmark with our
**GitHub Copilot CLI** models (gpt-5.5, etc.) and **no API keys** — auth is
transplanted from the host's `copilot login` session.

`pier_copilot_agent.py` is a custom [Pier](https://github.com/datacurve-ai/pier)
agent (`BaseInstalledAgent`). Pier ships agents for claude-code/codex/etc. but
not Copilot, and they expect API keys; this one drives `copilot --allow-all` and
injects the host credential instead.

## Why it works (the auth crack)
The interactive `copilot login` session is fully contained in
`~/.copilot/config.json` (~3.8KB: `copilotTokens` + `loggedInUsers`). Verified:
a fresh `$HOME` with only that file gives full model access (`--model gpt-5.5`).
The agent base64-injects it via `COPILOT_CONFIG_B64` into the sandbox — no volume
mount, no keyring. (`GH_TOKEN` alone only exposes the `default`/`auto` model.)

## Setup
```bash
git clone https://github.com/datacurve-ai/pier
git clone https://github.com/datacurve-ai/deep-swe
# Register the agent in the pier source:
cp pier_copilot_agent.py pier/src/pier/agents/installed/copilot.py
#  - add COPILOT = "copilot" to pier/src/pier/models/agent/name.py (AgentName)
#  - add `from .copilot import Copilot` + `Copilot,` to agents/factory.py (_AGENTS)
uv venv .pier-venv && uv pip install --python .pier-venv/bin/python -e ./pier
```

## Run
```bash
export COPILOT_CONFIG_B64=$(base64 -w0 ~/.copilot/config.json)   # auth, required
# baseline:
.pier-venv/bin/pier run -p deep-swe/tasks --agent copilot --model gpt-5.5 \
    --n-tasks 6 --sample-seed 0
# with an injected reasoning skill (baseline-vs-skill comparison):
export COPILOT_SKILL_B64=$(base64 -w0 path/to/megamind-deep/SKILL.md)
.pier-venv/bin/pier run -p deep-swe/tasks --agent copilot --model gpt-5.5 \
    --n-tasks 6 --sample-seed 0
```
Score = task verifier reward (1.0 = resolved). Objective, no judge.

## Gotchas (learned the hard way)
- **squid allowlist**: Pier's egress proxy is squid 6.x, which treats
  `.github.com` + `github.com` as a FATAL subdomain conflict. List only the
  wildcard form (`.github.com` already matches the apex).
- Sandbox needs node ≥ 22; the agent installs a portable node tarball + the
  `@github/copilot` npm package at environment-build time.
- `--allow-all` is required so Copilot doesn't block on trust/permission prompts
  non-interactively.
