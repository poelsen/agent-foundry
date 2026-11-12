"""The release workflow builds a tarball and runs `validate.py --tarball` on
it. That step runs only on a push to master, so this test builds the same
tarball and runs the same check where pull requests can see it fail."""

from __future__ import annotations

import subprocess
import sys
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
VERSION = "2099.01.01"
# The paths release.yml hands to `tar`, besides the VERSION file it writes.
RELEASE_PATHS = ("common", "cli", "tools/setup.py", "tools/foundry")


def _skip_build_artifacts(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    name = Path(info.name).name
    return None if name == "__pycache__" or name.endswith(".pyc") else info


def test_release_tarball_passes_validation(tmp_path: Path):
    version_file = tmp_path / "VERSION"
    version_file.write_text(f"{VERSION}\n")
    tarball = tmp_path / f"agent-foundry-{VERSION}.tar.gz"
    prefix = f"agent-foundry-{VERSION}"
    with tarfile.open(tarball, "w:gz") as tf:
        tf.add(version_file, arcname=f"{prefix}/VERSION")
        for rel in RELEASE_PATHS:
            tf.add(REPO_ROOT / rel, arcname=f"{prefix}/{rel}", filter=_skip_build_artifacts)

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "validate.py"), "--tarball", str(tarball)],
        capture_output=True, text=True, cwd=REPO_ROOT)

    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert "Tarball missing" not in result.stdout


def test_release_workflow_packs_the_paths_this_test_uses():
    """Keep RELEASE_PATHS honest against the workflow's tar command."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert "VERSION common/ cli/ tools/setup.py tools/foundry/" in workflow
