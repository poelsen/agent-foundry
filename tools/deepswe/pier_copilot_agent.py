"""GitHub Copilot CLI agent for Pier (DeepSWE), API-key-free.

Auth is transplanted from the host's interactive `copilot login` session: the
~/.copilot/config.json (which holds `copilotTokens` + `loggedInUsers`, ~3.8KB)
is passed in base64 via the COPILOT_CONFIG_B64 env var and written into the
sandbox. This is the only file needed for full model access (verified: a fresh
HOME with just config.json gives `copilot --model gpt-5.5`).

Run with:
    export COPILOT_CONFIG_B64=$(base64 -w0 ~/.copilot/config.json)
    pier run -p deep-swe/tasks/<id> --agent copilot --model gpt-5.5
"""

import re
import shlex

from pier.agents.installed.base import BaseInstalledAgent, with_prompt_template
from pier.environments.base import BaseEnvironment
from pier.models.agent.context import AgentContext
from pier.models.agent.install import AgentInstallSpec, InstallStep
from pier.models.agent.name import AgentName
from pier.models.agent.network import NetworkAllowlist

_NODE = "v22.14.0"


class Copilot(BaseInstalledAgent):
    @staticmethod
    def name() -> str:
        return AgentName.COPILOT.value

    def get_version_command(self) -> str | None:
        return 'export PATH="$HOME/.local/node/bin:$HOME/.local/bin:$PATH"; copilot --version'

    def parse_version(self, stdout: str) -> str:
        m = re.search(r"(\d+\.\d+\.\d+)", stdout)
        return m.group(1) if m else stdout.strip()

    def install_spec(self) -> AgentInstallSpec:
        root_run = (
            "if command -v apt-get >/dev/null 2>&1; then "
            "  apt-get update && apt-get install -y curl xz-utils ca-certificates; "
            "elif command -v apk >/dev/null 2>&1; then "
            "  apk add --no-cache curl xz libstdc++ ca-certificates; "
            "elif command -v yum >/dev/null 2>&1; then yum install -y curl xz; fi"
        )
        # Portable node (glibc x64) into ~/.local, then the Copilot CLI via npm.
        agent_run = (
            "set -eu; export PATH=\"$HOME/.local/node/bin:$HOME/.local/bin:$PATH\"; "
            "need=1; if command -v node >/dev/null 2>&1; then "
            "  maj=$(node -p 'process.versions.node.split(\".\")[0]' 2>/dev/null || echo 0); "
            "  [ \"$maj\" -ge 22 ] && need=0; fi; "
            "if [ \"$need\" = 1 ]; then mkdir -p \"$HOME/.local\"; "
            f"  curl -fsSL https://nodejs.org/dist/{_NODE}/node-{_NODE}-linux-x64.tar.xz "
            "    | tar -xJ -C \"$HOME/.local\"; "
            f"  ln -sfn \"$HOME/.local/node-{_NODE}-linux-x64\" \"$HOME/.local/node\"; "
            "  echo 'export PATH=\"$HOME/.local/node/bin:$HOME/.local/bin:$PATH\"' >> \"$HOME/.bashrc\"; fi; "
            "export PATH=\"$HOME/.local/node/bin:$PATH\"; "
            "npm install -g @github/copilot >/dev/null 2>&1; "
            "copilot --version"
        )
        return AgentInstallSpec(
            agent_name=self.name(),
            version=self._version,
            steps=[
                InstallStep(user="root", env={"DEBIAN_FRONTEND": "noninteractive"}, run=root_run),
                InstallStep(user="agent", run=agent_run),
            ],
            verification_command=self.get_version_command(),
        )

    def network_allowlist(self) -> NetworkAllowlist:
        # Copilot API + GitHub auth, plus install-time sources (node/npm).
        # NB: squid treats ".github.com" + "github.com" as a FATAL subdomain
        # conflict — ".github.com" already matches the apex, so don't also list
        # the bare domain. Same rule for any apex/wildcard pair.
        return NetworkAllowlist(domains=[
            ".github.com", ".githubcopilot.com", ".githubusercontent.com",
            "nodejs.org", ".npmjs.org",
        ])

    def populate_context_post_run(self, context: AgentContext) -> None:
        # Scoring is by the task verifier; no trajectory parsing needed.
        return None

    def _skills_setup(self) -> str:
        """Write an injected skill (base64 of a SKILL.md, via COPILOT_SKILL_B64)
        into the repo's .github/skills/ so Copilot loads it. Empty => baseline."""
        if not self._get_env("COPILOT_SKILL_B64"):
            return ""
        return (
            ' && mkdir -p .github/skills/injected '
            '&& printf %s "$COPILOT_SKILL_B64" | base64 -d '
            '> .github/skills/injected/SKILL.md'
        )

    @with_prompt_template
    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        cfg = self._get_env("COPILOT_CONFIG_B64")
        if not cfg:
            raise ValueError(
                "COPILOT_CONFIG_B64 not set — export "
                "COPILOT_CONFIG_B64=$(base64 -w0 ~/.copilot/config.json)"
            )
        model = (self.model_name or "auto").split("/")[-1]
        passthrough = {"COPILOT_CONFIG_B64": cfg}
        skill = self._get_env("COPILOT_SKILL_B64")
        if skill:
            passthrough["COPILOT_SKILL_B64"] = skill
        env = self.build_process_env(passthrough)
        path_export = 'export PATH="$HOME/.local/node/bin:$HOME/.local/bin:$PATH"'

        setup = (
            f'{path_export}; mkdir -p "$HOME/.copilot" && '
            'printf %s "$COPILOT_CONFIG_B64" | base64 -d > "$HOME/.copilot/config.json"'
            + self._skills_setup()
        )
        await self.exec_as_agent(environment, command=setup, env=env)

        escaped = shlex.quote(instruction)
        await self.exec_as_agent(
            environment,
            command=(
                f"{path_export}; copilot -p {escaped} --model {shlex.quote(model)} "
                "--allow-all --no-color 2>&1 | tee /logs/agent/copilot.txt"
            ),
            env=env,
        )
