from __future__ import annotations

import subprocess
from pathlib import Path

from rebake.utils.git import is_working_tree_clean


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
