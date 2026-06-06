#!/usr/bin/env python3
"""agent-foundry bootstrap shim.

Thin loader for the `foundry` package. Works in two modes:

1. Source mode: run as `python3 tools/setup.py ...` from a clone. The
   `foundry` package is a sibling under `tools/`.

2. Tarball mode: this file is deployed at `<project>/.foundry/setup.py`
   with a sibling `foundry.tar.gz`. The tarball is extracted to a tempdir
   (wiped at process exit) and the package is imported from there.

After loading, every public name from the `foundry` package is re-exported
here so legacy callers (`import setup`, `from setup import X`, and
`tools/validate.py`) keep working unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TARBALL_PATH: Path | None = None


def _bootstrap_root() -> Path:
    """Return the `tools/` dir that contains the `foundry` package.

    In tarball mode, first extract a sibling `foundry.tar.gz` to a tempdir
    (registered for cleanup at exit) and return the extracted `tools/` dir.
    In source mode, return the dir this file lives in (the `tools/` dir).
    """
    global _TARBALL_PATH
    setup_dir = Path(__file__).resolve().parent
    sibling_tarball = setup_dir / "foundry.tar.gz"
    if sibling_tarball.is_file():
        import atexit
        import shutil
        import tarfile
        import tempfile

        _TARBALL_PATH = sibling_tarball
        tmpdir = Path(tempfile.mkdtemp(prefix="foundry-"))
        atexit.register(shutil.rmtree, str(tmpdir), ignore_errors=True)
        with tarfile.open(sibling_tarball, "r:gz") as tf:
            try:
                tf.extractall(tmpdir, filter="data")
            except TypeError:
                # Python < 3.12 lacks the filter kwarg
                tf.extractall(tmpdir)
        # Strip a single top-level wrapper dir if present (matches GitHub
        # release tarball convention: `claude-foundry-vX.Y.Z/...`).
        entries = [p for p in tmpdir.iterdir() if not p.name.startswith(".")]
        root = entries[0] if (len(entries) == 1 and entries[0].is_dir()) else tmpdir
        return root / "tools"
    return setup_dir  # source mode: foundry package lives next to this file


sys.path.insert(0, str(_bootstrap_root()))

import foundry  # noqa: E402
from foundry import *  # noqa: E402, F403

# Wire up tarball-mode flags so the payload installer copies the existing
# canonical tarball instead of rebuilding one. The shim owns extraction,
# so it also owns these flags on the package's paths module.
if _TARBALL_PATH is not None:
    foundry.paths._TARBALL_MODE = True
    foundry.paths._PAYLOAD_TARBALL = _TARBALL_PATH

from foundry import main  # noqa: E402

if __name__ == "__main__":
    main()
