"""agent-foundry per-project setup package.

Re-exports the public API so external code can do either
``from foundry import X`` or ``import foundry; foundry.X``.

The legacy entrypoint ``tools/setup.py`` is now a thin bootstrap shim that
extracts a payload tarball when needed and re-exports everything here.
"""

from __future__ import annotations

from .console import GoBack, QuitSetup, ask_int, confirm, toggle_menu
from .deploy import (
    _command_skill_parent,
    _substitute_placeholders,
    copy_agents,
    copy_commands,
    copy_hooks,
    copy_learned_skills,
    copy_rules,
    copy_skills,
    discover_learned_categories,
    generate_settings_json,
    write_mcp_servers,
)
from .detect import (
    _read_dep_files,
    detect_languages,
    detect_platform,
    detect_templates,
    scan_extensions,
)
from .instructions import (
    generate_agent_foundry_header,
    generate_claude_md,
    has_agent_foundry_header,
    prepend_agent_foundry_header,
    update_agent_foundry_header,
)
from .manifest import (
    discover_projects,
    load_manifest,
    migrate_manifest,
    read_version,
    resolve_project_path,
    save_manifest,
)
from .orchestrator import (
    cmd_check,
    cmd_init,
    cmd_update_all,
    cmd_version,
    main,
)
from .paths import (
    AGENT_FOUNDRY_MARKER_END,
    AGENT_FOUNDRY_MARKER_START,
    AGENTS_DIR,
    COMMANDS_DIR,
    LEARNED_SKILLS_DIR,
    MCP_SERVERS_FILE,
    REPO_ROOT,
    _ensure_utf8_stdio,
    _resolve_repo_root,
)
from .payload import (
    _build_foundry_tarball,
    _ensure_gitignore_entry,
    _install_foundry_payload,
)
from .private import (
    _get_reserved_prefixes,
    clean_private_files,
    deploy_private_source,
    discover_private_content,
    redeploy_private_sources,
    validate_prefix,
)
from .registry import (
    BASE_RULES,
    ENVIRONMENT_SNIPPETS,
    FEATURE_PATHS,
    FEATURE_REQUIRED_SKILLS,
    FEATURE_SUGGESTED_SKILLS,
    HIDDEN_SKILLS,
    HOOK_SCRIPTS,
    LSP_PLUGINS,
    MANIFEST_MIGRATION,
    MODULAR_RULES,
    OPTIONAL_FEATURES,
    SKILL_GROUPS,
    SKILLS,
    WORKFLOW_PLUGINS,
)

__all__ = [
    # paths
    "AGENTS_DIR",
    "AGENT_FOUNDRY_MARKER_END",
    "AGENT_FOUNDRY_MARKER_START",
    # registry
    "BASE_RULES",
    "COMMANDS_DIR",
    "ENVIRONMENT_SNIPPETS",
    "FEATURE_PATHS",
    "FEATURE_REQUIRED_SKILLS",
    "FEATURE_SUGGESTED_SKILLS",
    "HIDDEN_SKILLS",
    "HOOK_SCRIPTS",
    "LEARNED_SKILLS_DIR",
    "LSP_PLUGINS",
    "MANIFEST_MIGRATION",
    "MCP_SERVERS_FILE",
    "MODULAR_RULES",
    "OPTIONAL_FEATURES",
    "REPO_ROOT",
    "SKILLS",
    "SKILL_GROUPS",
    "WORKFLOW_PLUGINS",
    # console
    "GoBack",
    "QuitSetup",
    # payload
    "_build_foundry_tarball",
    # deploy
    "_command_skill_parent",
    "_ensure_gitignore_entry",
    "_ensure_utf8_stdio",
    # private
    "_get_reserved_prefixes",
    "_install_foundry_payload",
    # detect
    "_read_dep_files",
    "_resolve_repo_root",
    "_substitute_placeholders",
    "ask_int",
    "clean_private_files",
    # orchestrator
    "cmd_check",
    "cmd_init",
    "cmd_update_all",
    "cmd_version",
    "confirm",
    "copy_agents",
    "copy_commands",
    "copy_hooks",
    "copy_learned_skills",
    "copy_rules",
    "copy_skills",
    "deploy_private_source",
    "detect_languages",
    "detect_platform",
    "detect_templates",
    "discover_learned_categories",
    "discover_private_content",
    # manifest
    "discover_projects",
    # instructions
    "generate_agent_foundry_header",
    "generate_claude_md",
    "generate_settings_json",
    "has_agent_foundry_header",
    "load_manifest",
    "main",
    "migrate_manifest",
    "prepend_agent_foundry_header",
    "read_version",
    "redeploy_private_sources",
    "resolve_project_path",
    "save_manifest",
    "scan_extensions",
    "toggle_menu",
    "update_agent_foundry_header",
    "validate_prefix",
    "write_mcp_servers",
]
