"""Per-project foundry payload: tarball build + setup.py install + gitignore."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import paths
from .manifest import read_version
from .registry import FEATURE_PATHS

# Names pruned anywhere in the source tree (caches, build artifacts, the
# maintainer's local .claude/ dev install).
_PAYLOAD_SKIP_ANYWHERE = {
    ".git", "__pycache__", ".pytest_cache", ".venv", "venv",
    "node_modules", "out", ".vscode-test", "dist", "build",
    ".coverage", "results", ".claude",
}

# Per-project payload dirs. These must only be pruned when they appear as
# DIRECT CHILDREN of src_root — pruning by basename anywhere would wrongly
# drop the `tools/foundry/` source package (basename "foundry").
_PAYLOAD_SKIP_TOPLEVEL = {
    ".foundry", ".foundry.new", ".foundry.old", "foundry",
}

# Combined set kept for backward compatibility with any external reference.
_PAYLOAD_SKIP_NAMES = _PAYLOAD_SKIP_ANYWHERE | _PAYLOAD_SKIP_TOPLEVEL

_GITIGNORE_HEADER = "# agent-foundry payload"


def _repo_root() -> Path:
    """Resolve the effective REPO_ROOT.

    Honors a ``REPO_ROOT`` override set on the top-level ``setup`` bootstrap
    shim module (the legacy single-module monkeypatch contract used by the
    test suite). Falls back to the canonical value from ``paths``.
    """
    shim = sys.modules.get("setup")
    if shim is not None:
        override = getattr(shim, "REPO_ROOT", None)
        if override is not None:
            return override
    return paths.REPO_ROOT


def _install_foundry_payload(
    project: Path, selected_features: list[str] | None = None,
) -> None:
    """Install foundry payload (tarball + setup.py) at <project>/.foundry/.

    Writes:
      <project>/.foundry/setup.py        — copy of the running script
      <project>/.foundry/foundry.tar.gz  — tarball of REPO_ROOT (or copy
                                           of the source tarball in
                                           tarball mode)

    Migrates: removes any legacy <project>/.claude/foundry/ tree and the
    obsolete .claude/.foundry.{new,old} staging dirs from older versions.

    Ensures <project>/.gitignore lists `.foundry/`.

    Skipped when REPO_ROOT lives inside the target project (running
    setup.py from a deployed payload against its own project — the
    payload is already canonical, no need to rewrite it).

    Args:
        project: Target project directory.
        selected_features: Keys from OPTIONAL_FEATURES the user opted
            into. Paths mapped in FEATURE_PATHS for features NOT in
            this list are excluded from the source-mode tarball build.
    """
    import atexit

    selected_features = selected_features or []
    project = project.resolve()
    repo_root = _repo_root()

    legacy_root = project / ".claude" / "foundry"
    foundry_dir = project / ".foundry"

    # Detect the migration boundary case: an old update-foundry.sh
    # extracted the new release into <project>/.claude/foundry/ and
    # invoked us from there. We can't delete the dir we're running from
    # mid-run (Linux survives via inode refcounting but it's racy;
    # Windows fails silently). Defer the legacy cleanup to atexit so the
    # dir is wiped only after Python exits.
    running_from_legacy = False
    if legacy_root.is_dir():
        try:
            repo_root.relative_to(legacy_root)
            running_from_legacy = True
        except ValueError:
            pass
        if not running_from_legacy:
            shutil.rmtree(legacy_root, ignore_errors=True)
            print(f"  Removed legacy foundry copy: {legacy_root}")

    for stale in (
        project / ".claude" / ".foundry.new",
        project / ".claude" / ".foundry.old",
        project / ".claude" / ".foundry-release.tar.gz",
    ):
        if stale.exists():
            if stale.is_dir():
                shutil.rmtree(stale, ignore_errors=True)
            else:
                stale.unlink()

    # Skip when REPO_ROOT is already canonical (deployed setup.py running
    # against its own project — payload is in place, nothing to write).
    try:
        repo_root.relative_to(foundry_dir)
        return
    except ValueError:
        pass

    # Skip when running setup.py from the foundry repo against itself
    # (no point tarballing the source we're sitting on into ./foundry/
    # inside it). The legacy-running case is allowed through — we still
    # need to install the new payload in that one.
    if not running_from_legacy:
        try:
            repo_root.relative_to(project)
            return
        except ValueError:
            pass

    foundry_dir.mkdir(parents=True, exist_ok=True)

    # Tarball: in tarball mode we already have the canonical artifact next
    # to the running setup.py — just make sure it lives at the canonical
    # path. In source mode, build a fresh tarball from REPO_ROOT.
    target_tarball = foundry_dir / "foundry.tar.gz"
    if (paths._TARBALL_MODE and paths._PAYLOAD_TARBALL is not None
            and paths._PAYLOAD_TARBALL.is_file()):
        if paths._PAYLOAD_TARBALL.resolve() != target_tarball.resolve():
            shutil.copy2(paths._PAYLOAD_TARBALL, target_tarball)
    else:
        _build_foundry_tarball(repo_root, target_tarball, selected_features)

    # setup.py copy: always refresh from REPO_ROOT so it matches the tarball
    src_setup = repo_root / "tools" / "setup.py"
    dst_setup = foundry_dir / "setup.py"
    shutil.copy2(src_setup, dst_setup)

    _ensure_gitignore_entry(project / ".gitignore", ".foundry/")
    # Delegate runtime state lives at <project>/.delegate/ when the
    # minimax-delegate feature is enabled — gitignore it too.
    if "minimax-delegate" in selected_features:
        _ensure_gitignore_entry(project / ".gitignore", ".delegate/")

    # If we were invoked from inside the legacy .claude/foundry/ tree,
    # defer its removal until after Python exits — we can't safely rmtree
    # the dir we're executing from while it's still in use.
    if running_from_legacy:
        atexit.register(shutil.rmtree, str(legacy_root), True)
        print(f"  Legacy {legacy_root} will be removed on exit")

    print(f"  Foundry payload installed at: {foundry_dir}")
    print(f"    Manual re-init: python3 {dst_setup} init {project}")


def _build_foundry_tarball(
    src_root: Path,
    out_path: Path,
    selected_features: list[str] | None = None,
) -> None:
    """Build a gzipped tarball of `src_root` at `out_path`.

    Excludes caches/build artifacts, the maintainer's local `.claude/`
    dev install, and any feature-gated paths the user didn't opt into.
    The tarball uses a top-level wrapper directory `agent-foundry-<ver>/`
    matching the GitHub release tarball convention.

    Writes to a `.tmp` sibling first and atomically renames into place
    so a crash mid-build never leaves a partial tarball.
    """
    import tarfile

    selected_features = selected_features or []
    excluded_abs: set[str] = set()
    for key, feature_paths in FEATURE_PATHS.items():
        if key in selected_features:
            continue
        for rel in feature_paths:
            excluded_abs.add(str((src_root / rel).resolve()))

    arc_root = f"agent-foundry-{read_version()}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    try:
        with tarfile.open(tmp_path, "w:gz") as tf:
            for root, dirs, files in os.walk(src_root, topdown=True):
                root_path = Path(root)
                at_top = root_path == src_root
                # Prune subdirs in-place to skip caches and feature-gated paths.
                # Per-project payload dirs (.foundry/, foundry/) are only pruned
                # at the top level so the `tools/foundry/` source package survives.
                kept_dirs = []
                for d in dirs:
                    if d in _PAYLOAD_SKIP_ANYWHERE:
                        continue
                    if at_top and d in _PAYLOAD_SKIP_TOPLEVEL:
                        continue
                    if str((root_path / d).resolve()) in excluded_abs:
                        continue
                    kept_dirs.append(d)
                dirs[:] = kept_dirs

                for fname in files:
                    if fname in _PAYLOAD_SKIP_ANYWHERE:
                        continue
                    if at_top and fname in _PAYLOAD_SKIP_TOPLEVEL:
                        continue
                    fpath = root_path / fname
                    if str(fpath.resolve()) in excluded_abs:
                        continue
                    arcname = f"{arc_root}/{fpath.relative_to(src_root).as_posix()}"
                    tf.add(fpath, arcname=arcname, recursive=False)
        tmp_path.replace(out_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _ensure_gitignore_entry(gitignore: Path, entry: str) -> None:
    """Append `entry` to `gitignore` if not already present.

    Matches both `.foundry/` and `.foundry` style entries to avoid duplicates.
    The `# agent-foundry payload` comment is emitted only on the first
    foundry entry; subsequent entries append directly to the same block.
    """
    needle = entry.rstrip("/")
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    for line in existing.splitlines():
        if line.strip().rstrip("/") == needle:
            return
    if existing and not existing.endswith("\n"):
        existing += "\n"
    if _GITIGNORE_HEADER in existing:
        new_content = existing + entry + "\n"
    else:
        new_content = existing + "\n" + _GITIGNORE_HEADER + "\n" + entry + "\n"
    gitignore.write_text(new_content, encoding="utf-8")
