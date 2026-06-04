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


def is_working_tree_clean(project_dir: Path = Path("."), *, allow_untracked_files: bool = False) -> bool:
    """Return True when there are no uncommitted changes in the working tree."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(project_dir),
    )
    lines = result.stdout.splitlines()
    if allow_untracked_files:
        # Untracked files are prefixed with "??" in porcelain output
        lines = [line for line in lines if not line.startswith("??")]
    return len(lines) == 0


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


def get_renamed_paths(project_dir: Path = Path(".")) -> dict[str, str]:
    """Return a map of original path -> current path for files renamed via git mv.

    Follows multi-step rename chains across the project's git history so a file
    moved A -> B -> C maps A directly to C. Paths are relative to project_dir.

    Only mappings whose original path no longer exists and whose destination
    currently exists are returned, so a path that was later recreated is ignored.
    """
    project_dir = project_dir.resolve()
    git_root = _git_root(project_dir)
    rel_prefix = str(project_dir.relative_to(git_root))

    result = subprocess.run(
        ["git", "log", "--reverse", "-M", "--diff-filter=R", "--name-status", "--format=", "--", "."],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(project_dir),
    )

    # Track each chain by its original path; reverse maps a current path back to
    # its origin so a follow-up rename extends the existing chain.
    origin_to_current: dict[str, str] = {}
    current_to_origin: dict[str, str] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not parts[0].startswith("R"):
            continue
        old = _strip_repo_prefix(parts[1], rel_prefix)
        new = _strip_repo_prefix(parts[2], rel_prefix)
        if old is None or new is None:
            continue
        origin = current_to_origin.pop(old, old)
        origin_to_current[origin] = new
        current_to_origin[new] = origin

    return {
        origin: current
        for origin, current in origin_to_current.items()
        if not (project_dir / origin).exists() and (project_dir / current).exists()
    }


def _strip_repo_prefix(path: str, rel_prefix: str) -> str | None:
    """Convert a repo-root-relative path to a project_dir-relative one."""
    if rel_prefix in ("", "."):
        return path
    prefix = rel_prefix.rstrip("/") + "/"
    if path.startswith(prefix):
        return path[len(prefix) :]
    return None


def redirect_patch_paths(patch: bytes, renames: dict[str, str]) -> bytes:
    """Rewrite diff header paths so hunks target their renamed destination.

    Substitutes the old path with the new path in the ``diff --git``, ``---``
    and ``+++`` header lines for each rename, leaving unrelated entries intact.
    """
    for old, new in renames.items():
        o = old.encode()
        n = new.encode()
        patch = patch.replace(b"diff --git a/" + o + b" b/" + o, b"diff --git a/" + n + b" b/" + n)
        patch = patch.replace(b"--- a/" + o + b"\n", b"--- a/" + n + b"\n")
        patch = patch.replace(b"+++ b/" + o + b"\n", b"+++ b/" + n + b"\n")
    return patch


def apply_patch(patch: bytes, project_dir: Path = Path(".")) -> tuple[bool, str]:
    """Apply a patch via git apply.

    Runs git apply from the git root with --directory so that patch paths
    (relative to the rendered template project) resolve correctly even when
    project_dir is a subdirectory of the git worktree.

    Attempts a clean apply first. On failure, falls back to --reject so that
    applicable hunks are still written and only conflicts end up as .rej files.
    Returns (all_hunks_applied, stderr).
    """
    git_root = _git_root(project_dir)
    directory = project_dir.relative_to(git_root)

    # Redirect hunks for files the user relocated with git mv to their new path
    renames = get_renamed_paths(project_dir)
    if renames:
        patch = redirect_patch_paths(patch, renames)

    cmd_base = ["git", "apply", "--ignore-whitespace"]
    # --directory=. causes git to produce invalid paths like ./file.txt
    if directory != Path("."):
        cmd_base.append(f"--directory={directory}")

    result = subprocess.run(
        [*cmd_base, "-"],
        input=patch,
        capture_output=True,
        cwd=str(git_root),
    )
    if result.returncode == 0:
        return True, ""

    # Partial fallback: apply what we can, write .rej files for conflicts
    result = subprocess.run(
        [*cmd_base, "--reject", "-"],
        input=patch,
        capture_output=True,
        cwd=str(git_root),
    )
    return False, result.stderr.decode(errors="replace")


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


def generate_diff(old_dir: Path, new_dir: Path) -> bytes:
    """Return a unified diff between two directories as a patch (bytes).

    Using bytes avoids UnicodeDecodeError when diffed directories contain
    binary files or files with non-UTF-8 content.
    """
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
            cwd=str(common),
        )
        raw = result.stdout
        old_prefix = (old_rel + "/").encode()
        new_prefix = (new_rel + "/").encode()
    else:
        result = subprocess.run(
            ["git", "diff", "--no-index", "--binary", str(old_real), str(new_real)],
            capture_output=True,
        )
        raw = result.stdout
        old_prefix = (str(old_real) + "/").encode()
        new_prefix = (str(new_real) + "/").encode()

    # git diff exits with 1 when there are differences; that is expected
    return raw.replace(old_prefix, b"").replace(new_prefix, b"")
