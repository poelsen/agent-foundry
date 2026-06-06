# Rules Overview

## Base Rules (Recommended for All Projects)

These rules are selected by default during `setup.py init` and copied to each project's `.claude/rules/`.

| Rule | Purpose |
|------|---------|
| agents.md | Agent orchestration and parallel execution |
| architecture.md | Module boundaries, file organization, design principles |
| coding-style.md | Functions, data/state, error handling, naming |
| git-workflow.md | Branching, commits, PRs |
| hooks.md | Pre/post tool hooks |
| performance.md | Model selection, context management |
| security.md | Security checklist and protocols |
| testing.md | TDD workflow, 80% coverage |
| codemaps.md | Codemap system, LSP plugins, architecture docs |
| skills.md | Learned skill discovery and reuse |

## Modular Rules (Choose Per-Project)

Copy or symlink from rule-library/ based on your project needs.

### By Language

| If using... | Add rule... |
|-------------|-------------|
| React | rule-library/lang/react.md |
| Node.js backend | rule-library/lang/nodejs.md |
| Python | rule-library/lang/python.md |
| Python + Qt | rule-library/lang/python-qt.md |
| C++ | rule-library/lang/cpp.md |
| C | rule-library/lang/c.md |
| Go | rule-library/lang/go.md |
| Rust | rule-library/lang/rust.md |
| Embedded C | rule-library/lang/c-embedded.md |
| MATLAB | rule-library/lang/matlab.md |

### By Project Type (Style)

| If building... | Add style... |
|----------------|--------------|
| Backend/API | rule-library/style/backend.md |
| Scripts/CLI | rule-library/style/scripts.md |
| Libraries | rule-library/style/library.md |
| Data pipelines | rule-library/style/data-pipeline.md |

### By Project Type (Architecture)

| If building... | Add arch... |
|----------------|-------------|
| REST API | rule-library/arch/rest-api.md |
| React app | rule-library/arch/react-app.md |
| Monolith | rule-library/arch/monolith.md |

### By Domain

| If building... | Add rule... |
|----------------|-------------|
| GUI/Frontend | rule-library/domain/gui.md |
| GUI threading | rule-library/domain/gui-threading.md |
| Embedded systems | rule-library/domain/embedded.md |
| Audio/DSP | rule-library/domain/dsp-audio.md |

### By Platform

| If hosted on... | Add rule... |
|-----------------|-------------|
| GitHub | rule-library/platform/github.md |

### By Security Level

| Project type | Add rule... |
|--------------|-------------|
| Production | rule-library/security/enterprise.md |
| Internal tools | rule-library/security/internal.md |
| Personal/sandbox | rule-library/security/sandbox.md |
