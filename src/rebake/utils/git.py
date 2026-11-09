from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path


def resolve_template_commit(template_url: str, checkout: str | None = None) -> str:
    """Return the commit hash a remote template repository ref points to.

    Branches and tags are resolved with git ls-remote for speed, avoiding
    a full clone. Anything ls-remote cannot resolve (e.g. a commit hash)
    falls back to a clone.
    """
    ref = "HEAD" if checkout is None else checkout
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
    return _get_commit_via_clone(template_url, ref)


def _get_commit_via_clone(template_url: str, ref: str) -> str:
    # A full clone is required: `git clone --branch` only accepts branches and tags
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(
            ["git", "clone", template_url, tmpdir],
            capture_output=True,
            check=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
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
    rel_prefix = (
        subprocess.run(
            ["git", "rev-parse", "--show-prefix"],
            capture_output=True,
            check=True,
            cwd=str(project_dir),
        )
        .stdout.decode(errors="surrogateescape")
        .rstrip("\n")
    )

    # A repository without commits has no history to follow
    has_head = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
        capture_output=True,
        cwd=str(project_dir),
    )
    if has_head.returncode != 0:
        return {}

    # -z emits raw NUL-separated paths; otherwise git C-quotes non-ASCII and special characters
    result = subprocess.run(
        ["git", "log", "-z", "--reverse", "-M", "--diff-filter=R", "--name-status", "--format=", "--", "."],
        capture_output=True,
        check=True,
        cwd=str(project_dir),
    )
    fields = iter(result.stdout.decode(errors="surrogateescape").split("\0"))

    # Each chain is [origin, current]; an origin that was recreated and moved
    # again starts a separate chain rather than extending the first one.
    chains: list[list[str]] = []
    chain_by_current: dict[str, list[str]] = {}
    # Rename records are "R<score>\0<old>\0<new>\0"; skip empty separators between commits
    for status in fields:
        if not status.startswith("R"):
            continue
        old = _strip_repo_prefix(next(fields), rel_prefix)
        new = _strip_repo_prefix(next(fields), rel_prefix)
        if old is None or new is None:
            continue
        chain = chain_by_current.pop(old, None)
        if chain is None:
            chain = [old, old]
            chains.append(chain)
        chain[1] = new
        chain_by_current[new] = chain

    destinations: dict[str, list[str]] = {}
    for origin, current in chains:
        if not (project_dir / origin).exists() and (project_dir / current).exists():
            destinations.setdefault(origin, []).append(current)
    # Several surviving destinations for one origin leave no single file to redirect to
    return {origin: currents[0] for origin, currents in destinations.items() if len(currents) == 1}


def _strip_repo_prefix(path: str, rel_prefix: str) -> str | None:
    """Convert a repo-root-relative path to a project_dir-relative one.

    rel_prefix is the output of `git rev-parse --show-prefix`: empty or ending with "/".
    """
    if path.startswith(rel_prefix):
        return path[len(rel_prefix) :]
    return None


def redirect_patch_paths(patch: bytes, renames: dict[str, str]) -> bytes:
    """Rewrite diff header paths so hunks target their renamed destination.

    Only entries that modify or delete an existing file are redirected. New-file
    entries are left intact so the template can create a file at a moved-from
    path. Rename and copy entries are also left intact, so a template rename of a
    user-moved file is not followed and fails to apply as it did before
    redirection existed. Hunk bodies are never touched.
    """
    if not renames:
        return patch
    return b"".join(_redirect_entry(entry, renames) for entry in _split_entries(patch))


def patch_target_paths(patch: bytes) -> list[str]:
    """Return the paths of existing files the patch modifies or deletes, i.e. the redirect candidates."""
    targets: list[str] = []
    for entry in _split_entries(patch):
        lines = entry.splitlines(keepends=True)
        target = _existing_file_target(lines[: _header_end(lines)])
        if target is not None:
            targets.append(target.decode(errors="surrogateescape"))
    return targets


def _split_entries(patch: bytes) -> list[bytes]:
    return re.split(rb"(?m)^(?=diff --git )", patch)


def _header_end(lines: list[bytes]) -> int:
    for i, line in enumerate(lines[1:], start=1):
        if line.startswith((b"@@", b"GIT binary patch")):
            return i
    return len(lines)


def _existing_file_target(header: list[bytes]) -> bytes | None:
    """Return the path of an entry that modifies or deletes an existing file, else None."""
    if not header or not header[0].startswith(b"diff --git "):
        return None
    if any(line.startswith((b"new file mode", b"rename from", b"copy from")) for line in header):
        return None
    return _parse_header_path(header[0])


def _redirect_entry(entry: bytes, renames: dict[str, str]) -> bytes:
    lines = entry.splitlines(keepends=True)
    header_end = _header_end(lines)
    header = lines[:header_end]

    o = _existing_file_target(header)
    if o is None:
        return entry
    new = renames.get(o.decode(errors="surrogateescape"))
    if new is None:
        return entry

    n = new.encode(errors="surrogateescape")
    rewritten = [b"diff --git " + _quote_path(b"a/" + n) + b" " + _quote_path(b"b/" + n) + b"\n"]
    for line in header[1:]:
        rewritten.append(
            _rewrite_file_line(line, b"--- ", b"a/", o, n) or _rewrite_file_line(line, b"+++ ", b"b/", o, n) or line
        )
    return b"".join(rewritten + lines[header_end:])


def _parse_header_path(line: bytes) -> bytes | None:
    """Return the unquoted path of a `diff --git` line whose a/ and b/ sides are the same file."""
    quoted = re.fullmatch(rb'diff --git "a/((?:[^"\\]|\\.)*)" "b/\1"\n?', line)
    if quoted is not None:
        return _unescape_c(quoted.group(1))
    match = re.fullmatch(rb"diff --git a/(.+) b/\1\n?", line)
    return None if match is None else match.group(1)


def _rewrite_file_line(line: bytes, marker: bytes, side: bytes, old: bytes, new: bytes) -> bytes | None:
    if not line.startswith(marker):
        return None
    body = line[len(marker) :].rstrip(b"\n")
    if _unquote_path(body.removesuffix(b"\t")) != side + old:
        return None
    # Like git, terminate paths containing spaces with a tab, whether quoted or not
    suffix = b"\t" if b" " in new else b""
    return marker + _quote_path(side + new) + suffix + line[len(marker) + len(body) :]


_C_UNESCAPES = {b"a": b"\a", b"b": b"\b", b"t": b"\t", b"n": b"\n", b"v": b"\v", b"f": b"\f", b"r": b"\r"}
_C_ESCAPES = {v[0]: b"\\" + k for k, v in _C_UNESCAPES.items()} | {ord('"'): b'\\"', ord("\\"): b"\\\\"}
_NEEDS_QUOTING = re.compile(rb'[\x00-\x1f"\\\x7f]')


def _unquote_path(path: bytes) -> bytes:
    """Decode a path that git C-quoted (e.g. "\\346\\227\\245.txt"); unquoted paths are returned as is."""
    if len(path) < 2 or not (path.startswith(b'"') and path.endswith(b'"')):
        return path
    return _unescape_c(path[1:-1])


def _unescape_c(escaped: bytes) -> bytes:
    """Decode the C escapes inside a git-quoted path, without the surrounding quotes."""

    def unescape(match: re.Match[bytes]) -> bytes:
        seq = match.group(1)
        if len(seq) == 3:
            return bytes([int(seq, 8)])
        return _C_UNESCAPES.get(seq, seq)

    return re.sub(rb"\\([0-7]{3}|.)", unescape, escaped)


def _quote_path(path: bytes) -> bytes:
    """C-quote a path when git apply could not read it verbatim; non-ASCII bytes are kept raw."""
    if _NEEDS_QUOTING.search(path) is None:
        return path
    escaped = _NEEDS_QUOTING.sub(lambda m: _C_ESCAPES.get(m.group(0)[0], b"\\%03o" % m.group(0)[0]), path)
    return b'"' + escaped + b'"'


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

    # Redirect hunks for files the user relocated with git mv to their new path.
    # The history scan is costly on long histories, so run it only when a target is missing.
    if any(not (project_dir / path).exists() for path in patch_target_paths(patch)):
        patch = redirect_patch_paths(patch, get_renamed_paths(project_dir))

    # A file the user already removed is in the state the template wants, but git
    # apply would fail on it ("No such file"), so leave it out of the patch.
    deletions: dict[str, bytes] = {}
    kept: list[bytes] = []
    for entry in _split_entries(patch):
        path = _deletion_path(entry)
        if path is not None:
            if not _lexists(project_dir / path):
                continue
            deletions[path] = entry
        kept.append(entry)
    patch = b"".join(kept)
    if not patch.strip():
        return True, ""

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
    # git apply --reject writes no .rej when a removal fails because the user
    # changed the file, so save the deletion diff itself as the conflict to resolve.
    for path, entry in deletions.items():
        target = project_dir / path
        if _lexists(target):
            target.with_name(target.name + ".rej").write_bytes(entry)
    return False, result.stderr.decode(errors="replace")


def _lexists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _deletion_path(entry: bytes) -> str | None:
    """Return the path of an entry that deletes an existing file, else None."""
    lines = entry.splitlines(keepends=True)
    header = lines[: _header_end(lines)]
    if not any(line.startswith(b"deleted file mode") for line in header):
        return None
    target = _existing_file_target(header)
    return None if target is None else target.decode(errors="surrogateescape")


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

    # core.quotePath=false keeps non-ASCII directory names raw so the prefix replacement below matches
    diff_cmd = ["git", "-c", "core.quotePath=false", "diff", "--no-index", "--binary"]
    # Run from the common ancestor with relative paths to avoid absolute-path and symlink quirks
    common = _common_ancestor(old_real, new_real)
    if common is not None:
        old_rel = str(old_real.relative_to(common))
        new_rel = str(new_real.relative_to(common))
        result = subprocess.run(
            [*diff_cmd, old_rel, new_rel],
            capture_output=True,
            cwd=str(common),
        )
        raw = result.stdout
        old_prefix = (old_rel + "/").encode()
        new_prefix = (new_rel + "/").encode()
    else:
        result = subprocess.run(
            [*diff_cmd, str(old_real), str(new_real)],
            capture_output=True,
        )
        raw = result.stdout
        old_prefix = (str(old_real) + "/").encode()
        new_prefix = (str(new_real) + "/").encode()

    # git diff exits with 1 when there are differences; that is expected
    return raw.replace(old_prefix, b"").replace(new_prefix, b"")
