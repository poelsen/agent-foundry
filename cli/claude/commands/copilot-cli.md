# /copilot-cli - One-Shot Prompt via Local Copilot CLI

Send a one-shot prompt to a non-Claude model through the local GitHub Copilot
CLI. Spends your GitHub Copilot subscription, not Anthropic tokens.

Arguments: $ARGUMENTS — first token is the model (e.g. `gpt-5.4`); the rest is
the prompt. If the first token is not a model name, treat the whole input as
the prompt and use the CLI default model.

Steps:

1. Read `.claude/skills/copilot-cli/SKILL.md` for the invocation contract.
2. Run the prerequisite check. If `copilot` is unavailable, tell the user it
   is not installed/authenticated and stop — do not substitute a Claude answer
   silently.
3. Run the canonical one-shot invocation with the parsed model and prompt.
4. Display the model's response, prefixed with which model produced it.
