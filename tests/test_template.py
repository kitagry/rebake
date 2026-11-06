from __future__ import annotations

from pathlib import Path

from rebake.utils.template import remove_skipped_paths


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")


def test_remove_skipped_paths_removes_exact_file(tmp_path: Path) -> None:
    _touch(tmp_path / "go.sum")
    _touch(tmp_path / "go.mod")

    remove_skipped_paths(tmp_path, ["go.sum"])

    assert not (tmp_path / "go.sum").exists()
    assert (tmp_path / "go.mod").exists()


def test_remove_skipped_paths_removes_directory_tree(tmp_path: Path) -> None:
    _touch(tmp_path / "docs" / "a.md")
    _touch(tmp_path / "docs" / "sub" / "b.md")

    remove_skipped_paths(tmp_path, ["docs"])

    assert not (tmp_path / "docs").exists()


def test_remove_skipped_paths_glob_matches_top_level_only(tmp_path: Path) -> None:
    # Mirrors cruft: patterns go through Path.glob, so "*.lock" is not recursive
    _touch(tmp_path / "uv.lock")
    _touch(tmp_path / "sub" / "poetry.lock")

    remove_skipped_paths(tmp_path, ["*.lock"])

    assert not (tmp_path / "uv.lock").exists()
    assert (tmp_path / "sub" / "poetry.lock").exists()


def test_remove_skipped_paths_recursive_glob(tmp_path: Path) -> None:
    _touch(tmp_path / "uv.lock")
    _touch(tmp_path / "sub" / "poetry.lock")

    remove_skipped_paths(tmp_path, ["**/*.lock"])

    assert not (tmp_path / "uv.lock").exists()
    assert not (tmp_path / "sub" / "poetry.lock").exists()


def test_remove_skipped_paths_ignores_missing_path(tmp_path: Path) -> None:
    _touch(tmp_path / "keep.txt")

    remove_skipped_paths(tmp_path, ["missing.txt", "*.nothing"])

    assert (tmp_path / "keep.txt").exists()


def test_remove_skipped_paths_never_touches_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _touch(root / "a.txt")
    outside = tmp_path / "outside.txt"
    _touch(outside)

    remove_skipped_paths(root, ["../outside.txt", str(outside)])

    assert outside.exists()


def test_remove_skipped_paths_unlinks_symlink_without_following(tmp_path: Path) -> None:
    root = tmp_path / "root"
    target_dir = tmp_path / "target"
    _touch(target_dir / "inner.txt")
    root.mkdir()
    (root / "link").symlink_to(target_dir, target_is_directory=True)

    remove_skipped_paths(root, ["link"])

    assert not (root / "link").exists()
    assert (target_dir / "inner.txt").exists()


def test_remove_skipped_paths_does_not_follow_symlinked_directory(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside_dir = tmp_path / "outside"
    _touch(outside_dir / "f.txt")
    root.mkdir()
    (root / "link").symlink_to(outside_dir, target_is_directory=True)

    remove_skipped_paths(root, ["link/f.txt", "link/*.txt", "**/*.txt"])

    assert (outside_dir / "f.txt").exists()


def test_remove_skipped_paths_ignores_absolute_glob(tmp_path: Path) -> None:
    _touch(tmp_path / "a.lock")

    remove_skipped_paths(tmp_path, [str(tmp_path / "*.lock")])

    assert (tmp_path / "a.lock").exists()
