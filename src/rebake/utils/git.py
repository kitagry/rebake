from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def get_template_head_commit(template_url: str, checkout: str | None = None) -> str:
    """Return the HEAD commit hash of a remote template repository.

    Uses git ls-remote for speed, avoiding a full clone.
    Falls back to a shallow clone when checkout is a bare commit hash
    that ls-remote cannot resolve.
    """
    ref = checkout or "HEAD"
    try:
        result = subprocess.run(
            ["git", "ls-remote", template_url, ref],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = result.stdout.strip().splitlines()
        if lines:
            return lines[0].split("\t")[0]
    except subprocess.CalledProcessError:
        pass

    # ls-remote returns nothing when checkout is a commit hash, so clone instead
    return _get_commit_via_clone(template_url, checkout)


def _get_commit_via_clone(template_url: str, checkout: str | None) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_args = ["git", "clone", "--depth=1"]
        if checkout:
            clone_args += ["--branch", checkout]
        clone_args += [template_url, tmpdir]
        subprocess.run(clone_args, capture_output=True, check=True)

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=tmpdir,
        )
        return result.stdout.strip()


def clone_at_commit(template_url: str, commit: str, dest: Path) -> None:
    """Clone the template repository and check out the given commit."""
    subprocess.run(
        ["git", "clone", template_url, str(dest)],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "checkout", commit],
        capture_output=True,
        check=True,
        cwd=str(dest),
    )


def is_working_tree_clean(project_dir: Path = Path(".")) -> bool:
    """Return True when there are no uncommitted changes in the working tree."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(project_dir),
    )
    return result.stdout.strip() == ""


def apply_patch(patch: str, project_dir: Path = Path("."), three_way: bool = True) -> bool:
    """Apply a patch string via git apply.

    When three_way is True, passes -3 so conflicts become inline markers
    instead of .rej files.  Returns True on success.
    """
    args = ["git", "apply"]
    if three_way:
        args.append("-3")
    args.append("-")

    result = subprocess.run(
        args,
        input=patch,
        capture_output=True,
        text=True,
        cwd=str(project_dir),
    )
    return result.returncode == 0


def generate_diff(old_dir: Path, new_dir: Path) -> str:
    """Return a unified diff between two directories as a patch string."""
    result = subprocess.run(
        ["git", "diff", "--no-index", str(old_dir), str(new_dir)],
        capture_output=True,
        text=True,
    )
    # git diff exits with 1 when there are differences; that is expected
    raw = result.stdout
    # Normalize absolute temp paths to relative paths for git apply
    old_prefix = str(old_dir) + "/"
    new_prefix = str(new_dir) + "/"
    return raw.replace(old_prefix, "").replace(new_prefix, "")
