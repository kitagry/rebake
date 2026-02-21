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


def _git_root(project_dir: Path) -> Path:
    """Return the root of the git worktree containing project_dir."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(project_dir),
    )
    return Path(result.stdout.strip())


def apply_patch(patch: str, project_dir: Path = Path(".")) -> tuple[bool, str]:
    """Apply a patch string via git apply.

    Runs git apply from the git root with --directory so that patch paths
    (relative to the rendered template project) resolve correctly even when
    project_dir is a subdirectory of the git worktree.

    Attempts a clean apply first. On failure, falls back to --reject so that
    applicable hunks are still written and only conflicts end up as .rej files.
    Returns (all_hunks_applied, stderr).
    """
    git_root = _git_root(project_dir)
    directory = project_dir.relative_to(git_root)
    cmd_base = ["git", "apply", "--ignore-whitespace", f"--directory={directory}"]

    result = subprocess.run(
        [*cmd_base, "-"],
        input=patch,
        capture_output=True,
        text=True,
        cwd=str(git_root),
    )
    if result.returncode == 0:
        return True, ""

    # Partial fallback: apply what we can, write .rej files for conflicts
    result = subprocess.run(
        [*cmd_base, "--reject", "-"],
        input=patch,
        capture_output=True,
        text=True,
        cwd=str(git_root),
    )
    return False, result.stderr


def _common_ancestor(path1: Path, path2: Path) -> Path | None:
    """Return the deepest common directory ancestor of two absolute paths."""
    common_parts: list[str] = []
    for a, b in zip(path1.parts, path2.parts):
        if a == b:
            common_parts.append(a)
        else:
            break
    if len(common_parts) <= 1:  # only the filesystem root
        return None
    return Path(*common_parts)


def generate_diff(old_dir: Path, new_dir: Path) -> str:
    """Return a unified diff between two directories as a patch string."""
    old_real = old_dir.resolve()
    new_real = new_dir.resolve()

    # Run from the common ancestor with relative paths to avoid absolute-path and symlink quirks
    common = _common_ancestor(old_real, new_real)
    if common is not None:
        old_rel = str(old_real.relative_to(common))
        new_rel = str(new_real.relative_to(common))
        result = subprocess.run(
            ["git", "diff", "--no-index", "--binary", old_rel, new_rel],
            capture_output=True,
            text=True,
            cwd=str(common),
        )
        raw = result.stdout
        old_prefix = old_rel + "/"
        new_prefix = new_rel + "/"
    else:
        result = subprocess.run(
            ["git", "diff", "--no-index", "--binary", str(old_real), str(new_real)],
            capture_output=True,
            text=True,
        )
        raw = result.stdout
        old_prefix = str(old_real) + "/"
        new_prefix = str(new_real) + "/"

    # git diff exits with 1 when there are differences; that is expected
    return raw.replace(old_prefix, "").replace(new_prefix, "")
