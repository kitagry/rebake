from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rebake.utils.git import (
    apply_patch,
    generate_diff,
    get_renamed_paths,
    is_working_tree_clean,
    redirect_patch_paths,
    resolve_template_commit,
)


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)


def _commit_all(path: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=path, check=True, capture_output=True)


def test_get_renamed_paths_detects_git_mv(tmp_path: Path) -> None:
    """A file moved via git mv should map old path -> new path."""
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("hello\n")
    _commit_all(tmp_path, "initial")

    (tmp_path / "docs").mkdir()
    subprocess.run(["git", "mv", "README.md", "docs/README.md"], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "move readme")

    renames = get_renamed_paths(tmp_path)

    assert renames == {"README.md": "docs/README.md"}


def test_get_renamed_paths_follows_multi_step_rename_chain(tmp_path: Path) -> None:
    """A file moved twice should map the original path to the final path."""
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("content\n")
    _commit_all(tmp_path, "initial")

    subprocess.run(["git", "mv", "a.txt", "b.txt"], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "rename to b")

    subprocess.run(["git", "mv", "b.txt", "c.txt"], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "rename to c")

    renames = get_renamed_paths(tmp_path)

    assert renames == {"a.txt": "c.txt"}


def test_get_renamed_paths_ignores_recreated_origin(tmp_path: Path) -> None:
    """If a file is recreated at the original path, it should not be redirected."""
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("hello\n")
    _commit_all(tmp_path, "initial")

    (tmp_path / "docs").mkdir()
    subprocess.run(["git", "mv", "README.md", "docs/README.md"], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "move readme")

    # Recreate a file at the original location
    (tmp_path / "README.md").write_text("new readme\n")
    _commit_all(tmp_path, "recreate readme")

    renames = get_renamed_paths(tmp_path)

    assert "README.md" not in renames


def test_get_renamed_paths_returns_empty_without_renames(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("hello\n")
    _commit_all(tmp_path, "initial")

    assert get_renamed_paths(tmp_path) == {}


def test_redirect_patch_paths_rewrites_modified_file_paths() -> None:
    patch = (
        b"diff --git a/README.md b/README.md\n"
        b"index 1234567..89abcde 100644\n"
        b"--- a/README.md\n"
        b"+++ b/README.md\n"
        b"@@ -1 +1 @@\n"
        b"-hello\n"
        b"+world\n"
    )

    result = redirect_patch_paths(patch, {"README.md": "docs/README.md"})

    assert b"diff --git a/docs/README.md b/docs/README.md\n" in result
    assert b"--- a/docs/README.md\n" in result
    assert b"+++ b/docs/README.md\n" in result
    assert b"a/README.md" not in result


def test_redirect_patch_paths_leaves_unrelated_paths_untouched() -> None:
    patch = b"diff --git a/other.md b/other.md\n--- a/other.md\n+++ b/other.md\n@@ -1 +1 @@\n-a\n+b\n"

    result = redirect_patch_paths(patch, {"README.md": "docs/README.md"})

    assert result == patch


def test_redirect_patch_paths_does_not_match_path_prefix() -> None:
    """A rename header whose new path merely starts with the moved path must stay intact."""
    patch = b"diff --git a/x b/xy\nsimilarity index 90%\nrename from x\nrename to xy\n"

    result = redirect_patch_paths(patch, {"x": "docs/x"})

    assert result == patch


@pytest.fixture
def template_repo(tmp_path: Path) -> tuple[str, str]:
    """A local git repo with a tag and a branch. Returns (url, head_commit)."""
    repo = tmp_path / "template"
    repo.mkdir()
    _init_repo(repo)
    (repo / "file.txt").write_text("v1\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "tag", "v1.0.0"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "branch", "feature"], cwd=repo, check=True, capture_output=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    return str(repo), head


def test_resolve_template_commit_without_checkout(template_repo: tuple[str, str]) -> None:
    url, head = template_repo
    assert resolve_template_commit(url) == head


def test_resolve_template_commit_with_branch(template_repo: tuple[str, str]) -> None:
    url, head = template_repo
    assert resolve_template_commit(url, checkout="feature") == head


def test_resolve_template_commit_with_tag(template_repo: tuple[str, str]) -> None:
    url, head = template_repo
    assert resolve_template_commit(url, checkout="v1.0.0") == head


def test_resolve_template_commit_with_full_sha(template_repo: tuple[str, str]) -> None:
    url, head = template_repo
    assert resolve_template_commit(url, checkout=head) == head


def test_resolve_template_commit_with_short_sha(template_repo: tuple[str, str]) -> None:
    url, head = template_repo
    assert resolve_template_commit(url, checkout=head[:7]) == head


def test_resolve_template_commit_with_nonexistent_ref(template_repo: tuple[str, str]) -> None:
    url, _ = template_repo
    with pytest.raises(subprocess.CalledProcessError):
        resolve_template_commit(url, checkout="no-such-ref")


def test_resolve_template_commit_with_nonexistent_full_sha(template_repo: tuple[str, str]) -> None:
    url, _ = template_repo
    with pytest.raises(subprocess.CalledProcessError):
        resolve_template_commit(url, checkout="0" * 40)


def test_is_working_tree_clean_allows_untracked_when_flag_set(tmp_path: Path) -> None:
    """When only untracked files exist, allow_untracked_files=True should return True."""
    _init_repo(tmp_path)
    (tmp_path / "untracked.txt").write_text("hello")

    # Without flag: untracked files count as dirty
    assert not is_working_tree_clean(tmp_path)

    # With flag: untracked files are ignored
    assert is_working_tree_clean(tmp_path, allow_untracked_files=True)


def test_is_working_tree_clean_rejects_modified_tracked_files_even_with_flag(tmp_path: Path) -> None:
    """Even with allow_untracked_files=True, modifications to tracked files should be dirty."""
    _init_repo(tmp_path)

    tracked = tmp_path / "tracked.txt"
    tracked.write_text("original")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)

    tracked.write_text("modified")

    assert not is_working_tree_clean(tmp_path, allow_untracked_files=True)


def test_generate_diff_with_binary_file(tmp_path: Path) -> None:
    """generate_diff should not raise UnicodeDecodeError for binary files."""
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()

    # Write a file with non-UTF-8 bytes (simulates binary content)
    (old_dir / "data.bin").write_bytes(b"\xff\xfe\x00\x01")
    (new_dir / "data.bin").write_bytes(b"\xff\xfe\x00\x02")

    # Should not raise UnicodeDecodeError
    patch = generate_diff(old_dir, new_dir)
    assert isinstance(patch, bytes)
    assert len(patch) > 0


def test_generate_diff_returns_bytes(tmp_path: Path) -> None:
    """generate_diff should return bytes."""
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()

    (old_dir / "file.txt").write_text("hello\n")
    (new_dir / "file.txt").write_text("world\n")

    patch = generate_diff(old_dir, new_dir)
    assert isinstance(patch, bytes)


def test_apply_patch_with_binary_content(tmp_path: Path) -> None:
    """apply_patch should handle binary patches without UnicodeDecodeError."""
    _init_repo(tmp_path)

    # Create initial binary file and commit it
    (tmp_path / "data.bin").write_bytes(b"\xff\xfe\x00\x01")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)

    # Generate a patch with old and new versions
    old_dir = tmp_path / "old_render"
    new_dir = tmp_path / "new_render"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "data.bin").write_bytes(b"\xff\xfe\x00\x01")
    (new_dir / "data.bin").write_bytes(b"\xff\xfe\x00\x02")

    patch = generate_diff(old_dir, new_dir)
    assert isinstance(patch, bytes)

    # Applying the patch should not raise UnicodeDecodeError
    success, _ = apply_patch(patch, tmp_path)
    assert success


def test_apply_patch_redirects_to_git_moved_file(tmp_path: Path) -> None:
    """A patch targeting a file moved via git mv should apply at the new path."""
    _init_repo(tmp_path)

    (tmp_path / "README.md").write_text("hello\n")
    _commit_all(tmp_path, "initial")

    (tmp_path / "docs").mkdir()
    subprocess.run(["git", "mv", "README.md", "docs/README.md"], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "move readme")

    # Template diff still references the original (pre-move) path
    old_dir = tmp_path / "old_render"
    new_dir = tmp_path / "new_render"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "README.md").write_text("hello\n")
    (new_dir / "README.md").write_text("hello world\n")

    patch = generate_diff(old_dir, new_dir)

    success, stderr = apply_patch(patch, tmp_path)

    assert success, stderr
    assert (tmp_path / "docs" / "README.md").read_text() == "hello world\n"
    assert not (tmp_path / "README.md").exists()


def test_apply_patch_redirects_git_moved_file_in_subdirectory(tmp_path: Path) -> None:
    """A move inside a target sub-directory should redirect paths relative to that sub-directory."""
    _init_repo(tmp_path)
    target = tmp_path / "services" / "api"
    target.mkdir(parents=True)
    (target / "config.txt").write_text("hello\n")
    _commit_all(tmp_path, "initial")

    (target / "conf").mkdir()
    subprocess.run(
        ["git", "mv", "services/api/config.txt", "services/api/conf/config.txt"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    _commit_all(tmp_path, "move config")

    old_dir = tmp_path / "old_render"
    new_dir = tmp_path / "new_render"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "config.txt").write_text("hello\n")
    (new_dir / "config.txt").write_text("hello world\n")

    patch = generate_diff(old_dir, new_dir)

    success, stderr = apply_patch(patch, target)

    assert success, stderr
    assert (target / "conf" / "config.txt").read_text() == "hello world\n"
    assert not (target / "config.txt").exists()


def test_get_renamed_paths_returns_empty_without_commits(tmp_path: Path) -> None:
    """A repository with no commits yet has no rename history to follow."""
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("hello\n")

    assert get_renamed_paths(tmp_path) == {}


def test_get_renamed_paths_skips_ambiguous_chain_after_origin_recreated(tmp_path: Path) -> None:
    """If an origin path is recreated and moved again, its template file has no single destination."""
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("first file\n" * 5)
    _commit_all(tmp_path, "initial")
    subprocess.run(["git", "mv", "a.txt", "b.txt"], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "a -> b")
    (tmp_path / "a.txt").write_text("second file\n" * 5)
    _commit_all(tmp_path, "recreate a")
    subprocess.run(["git", "mv", "a.txt", "c.txt"], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "a -> c")
    subprocess.run(["git", "mv", "b.txt", "d.txt"], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "b -> d")

    assert "a.txt" not in get_renamed_paths(tmp_path)


def test_redirect_patch_paths_rewrites_deleted_file_entry() -> None:
    patch = b"diff --git a/x b/x\ndeleted file mode 100644\n--- a/x\n+++ /dev/null\n@@ -1 +0,0 @@\n-a\n"

    result = redirect_patch_paths(patch, {"x": "docs/x"})

    assert result == (
        b"diff --git a/docs/x b/docs/x\ndeleted file mode 100644\n--- a/docs/x\n+++ /dev/null\n@@ -1 +0,0 @@\n-a\n"
    )


def test_redirect_patch_paths_leaves_new_file_entry_untouched() -> None:
    """A template adding a file at a path the user moved away from must create it there."""
    patch = b"diff --git a/x b/x\nnew file mode 100644\n--- /dev/null\n+++ b/x\n@@ -0,0 +1 @@\n+a\n"

    result = redirect_patch_paths(patch, {"x": "docs/x"})

    assert result == patch


def test_redirect_patch_paths_leaves_template_rename_entry_untouched() -> None:
    patch = (
        b"diff --git a/x b/y\nsimilarity index 80%\nrename from x\nrename to y\n--- a/x\n+++ b/y\n@@ -1 +1 @@\n-a\n+b\n"
    )

    result = redirect_patch_paths(patch, {"x": "docs/x"})

    assert result == patch


def test_redirect_patch_paths_does_not_rewrite_hunk_body() -> None:
    """Lines inside a hunk that look like headers are file content, not patch headers."""
    patch = (
        b"diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1,2 +1,2 @@\n---- a/x\n-+++ b/x\n+diff --git a/x b/x\n+changed\n"
    )

    result = redirect_patch_paths(patch, {"x": "docs/x"})

    assert result == (
        b"diff --git a/docs/x b/docs/x\n--- a/docs/x\n+++ b/docs/x\n@@ -1,2 +1,2 @@\n"
        b"---- a/x\n"
        b"-+++ b/x\n"
        b"+diff --git a/x b/x\n"
        b"+changed\n"
    )


def test_apply_patch_redirects_moved_file_with_space_in_name(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "my file.txt").write_text("hello\n")
    _commit_all(tmp_path, "initial")
    (tmp_path / "docs").mkdir()
    subprocess.run(["git", "mv", "my file.txt", "docs/my file.txt"], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "move")

    old_dir = tmp_path / "old_render"
    new_dir = tmp_path / "new_render"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "my file.txt").write_text("hello\n")
    (new_dir / "my file.txt").write_text("hello world\n")

    success, stderr = apply_patch(generate_diff(old_dir, new_dir), tmp_path)

    assert success, stderr
    assert (tmp_path / "docs" / "my file.txt").read_text() == "hello world\n"


def test_apply_patch_keeps_other_files_when_template_renames_moved_file(tmp_path: Path) -> None:
    """A template rename of a user-moved file must not make the whole patch malformed."""
    _init_repo(tmp_path)
    (tmp_path / "x.txt").write_text("".join(f"line{i}\n" for i in range(10)))
    (tmp_path / "other.txt").write_text("old\n")
    _commit_all(tmp_path, "initial")
    (tmp_path / "docs").mkdir()
    subprocess.run(["git", "mv", "x.txt", "docs/x.txt"], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "move")

    old_dir = tmp_path / "old_render"
    new_dir = tmp_path / "new_render"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "x.txt").write_text("".join(f"line{i}\n" for i in range(10)))
    (new_dir / "y.txt").write_text("".join(f"line{i}\n" for i in range(10)) + "extra\n")
    (old_dir / "other.txt").write_text("old\n")
    (new_dir / "other.txt").write_text("new\n")

    apply_patch(generate_diff(old_dir, new_dir), tmp_path)

    assert (tmp_path / "other.txt").read_text() == "new\n"
