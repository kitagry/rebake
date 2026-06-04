from __future__ import annotations

import subprocess
from pathlib import Path

from rebake.utils.git import (
    apply_patch,
    generate_diff,
    get_renamed_paths,
    is_working_tree_clean,
    redirect_patch_paths,
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
