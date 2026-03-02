from __future__ import annotations

import subprocess
from pathlib import Path

from rebake.utils.git import apply_patch, generate_diff, is_working_tree_clean


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)


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
    success, stderr = apply_patch(patch, tmp_path)
    assert success
