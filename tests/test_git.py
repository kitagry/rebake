from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rebake.utils.git import (
    apply_patch,
    generate_diff,
    get_renamed_paths,
    is_working_tree_clean,
    patch_target_paths,
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

    assert get_renamed_paths(tmp_path) == {}


def test_get_renamed_paths_ignores_chain_whose_destination_was_deleted(tmp_path: Path) -> None:
    """Only chains that still end at an existing file count as candidate destinations."""
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("first file\n" * 5)
    _commit_all(tmp_path, "initial")
    subprocess.run(["git", "mv", "a.txt", "b.txt"], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "a -> b")
    (tmp_path / "b.txt").unlink()
    (tmp_path / "a.txt").write_text("second file\n" * 5)
    _commit_all(tmp_path, "delete b, recreate a")
    subprocess.run(["git", "mv", "a.txt", "c.txt"], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "a -> c")

    assert get_renamed_paths(tmp_path) == {"a.txt": "c.txt"}


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

    success, _ = apply_patch(generate_diff(old_dir, new_dir), tmp_path)

    # Template renames of moved files are not followed; they are reported as conflicts
    assert not success
    assert (tmp_path / "other.txt").read_text() == "new\n"
    assert (tmp_path / "docs" / "x.txt").read_text() == "".join(f"line{i}\n" for i in range(10))


@pytest.fixture
def quoted_git_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force git's default C-quoting of non-ASCII paths regardless of the developer's global config."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.quotePath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")


@pytest.mark.usefixtures("quoted_git_paths")
@pytest.mark.parametrize(
    ("origin", "destination"),
    [
        ("日本語.txt", "ドキュメント/日本語.txt"),
        ('quote"d.txt', "docs/back\\slash.txt"),
        ("tab\tname.txt", "docs/with space.txt"),
    ],
)
def test_get_renamed_paths_detects_git_mv_of_quoted_path(tmp_path: Path, origin: str, destination: str) -> None:
    _init_repo(tmp_path)
    (tmp_path / origin).write_text("hello\n")
    _commit_all(tmp_path, "initial")
    (tmp_path / destination).parent.mkdir(exist_ok=True)
    subprocess.run(["git", "mv", origin, destination], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "move")

    assert get_renamed_paths(tmp_path) == {origin: destination}


def test_redirect_patch_paths_rewrites_quoted_header_paths() -> None:
    """git C-quotes non-ASCII paths in diff headers; they must be unquoted to match renames."""
    patch = (
        b'diff --git "a/\\346\\227\\245.txt" "b/\\346\\227\\245.txt"\n'
        b"index 1111111..2222222 100644\n"
        b'--- "a/\\346\\227\\245.txt"\n'
        b'+++ "b/\\346\\227\\245.txt"\n'
        b"@@ -1 +1 @@\n-hello\n+hello world\n"
    )

    result = redirect_patch_paths(patch, {"日.txt": "docs/日.txt"})

    assert (
        result
        == (
            "diff --git a/docs/日.txt b/docs/日.txt\n"
            "index 1111111..2222222 100644\n"
            "--- a/docs/日.txt\n"
            "+++ b/docs/日.txt\n"
            "@@ -1 +1 @@\n-hello\n+hello world\n"
        ).encode()
    )


def test_redirect_patch_paths_quotes_destination_with_special_characters() -> None:
    patch = b"diff --git a/x b/x\nindex 1111111..2222222 100644\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"

    result = redirect_patch_paths(patch, {"x": 'docs/q"\\\t.txt'})

    assert result == (
        b'diff --git "a/docs/q\\"\\\\\\t.txt" "b/docs/q\\"\\\\\\t.txt"\n'
        b"index 1111111..2222222 100644\n"
        b'--- "a/docs/q\\"\\\\\\t.txt"\n'
        b'+++ "b/docs/q\\"\\\\\\t.txt"\n'
        b"@@ -1 +1 @@\n-a\n+b\n"
    )


@pytest.mark.usefixtures("quoted_git_paths")
@pytest.mark.parametrize(
    ("origin", "destination"),
    [
        ("日本語.txt", "ドキュメント/日本語.txt"),
        ('quote"d.txt', "docs/back\\slash.txt"),
        ("tab\tname.txt", "docs/with space.txt"),
    ],
)
def test_apply_patch_redirects_git_moved_file_with_quoted_path(tmp_path: Path, origin: str, destination: str) -> None:
    _init_repo(tmp_path)
    (tmp_path / origin).write_text("hello\n")
    _commit_all(tmp_path, "initial")
    (tmp_path / destination).parent.mkdir(exist_ok=True)
    subprocess.run(["git", "mv", origin, destination], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "move")

    old_dir = tmp_path / "old_render"
    new_dir = tmp_path / "new_render"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / origin).write_text("hello\n")
    (new_dir / origin).write_text("hello world\n")

    success, stderr = apply_patch(generate_diff(old_dir, new_dir), tmp_path)

    assert success, stderr
    assert (tmp_path / destination).read_text() == "hello world\n"
    assert not (tmp_path / origin).exists()


def test_patch_target_paths_lists_modified_and_deleted_files_only() -> None:
    """Only entries that expect an existing file are candidates for redirection."""
    patch = (
        b"diff --git a/mod.txt b/mod.txt\n--- a/mod.txt\n+++ b/mod.txt\n@@ -1 +1 @@\n-a\n+b\n"
        b"diff --git a/del.txt b/del.txt\ndeleted file mode 100644\n--- a/del.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-a\n"
        b"diff --git a/new.txt b/new.txt\nnew file mode 100644\n--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+a\n"
        b"diff --git a/old.txt b/renamed.txt\nsimilarity index 100%\nrename from old.txt\nrename to renamed.txt\n"
        b'diff --git "a/\\346\\227\\245.txt" "b/\\346\\227\\245.txt"\n--- "a/\\346\\227\\245.txt"\n'
        b'+++ "b/\\346\\227\\245.txt"\n@@ -1 +1 @@\n-a\n+b\n'
    )

    assert patch_target_paths(patch) == ["mod.txt", "del.txt", "日.txt"]


@pytest.mark.usefixtures("quoted_git_paths")
def test_generate_diff_strips_non_ascii_render_directory(tmp_path: Path) -> None:
    """A non-ASCII project slug must not leak into patch paths through git's C-quoting."""
    old_dir = tmp_path / "old" / "日本"
    new_dir = tmp_path / "new" / "日本"
    old_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)
    (old_dir / "x.txt").write_text("a\n")
    (new_dir / "x.txt").write_text("b\n")

    patch = generate_diff(old_dir, new_dir)

    assert patch.splitlines()[0] == b"diff --git a/x.txt b/x.txt"


def test_redirect_patch_paths_tab_terminates_quoted_destination_with_space() -> None:
    """git ends ---/+++ paths containing spaces with a tab even when the path is quoted."""
    patch = b"diff --git a/x b/x\nindex 1111111..2222222 100644\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"

    result = redirect_patch_paths(patch, {"x": 'docs/q" s.txt'})

    assert b'--- "a/docs/q\\" s.txt"\t\n' in result
    assert b'+++ "b/docs/q\\" s.txt"\t\n' in result


def _render_dirs(tmp_path: Path) -> tuple[Path, Path]:
    old_dir = tmp_path / "old_render"
    new_dir = tmp_path / "new_render"
    old_dir.mkdir()
    new_dir.mkdir()
    return old_dir, new_dir


def test_apply_patch_writes_rej_when_template_deletes_locally_modified_file(tmp_path: Path) -> None:
    """git apply --reject writes no .rej for a failed removal, so the conflict must be saved explicitly."""
    _init_repo(tmp_path)
    (tmp_path / "gone.txt").write_text("a\nb\nlocal\n")
    (tmp_path / "other.txt").write_text("old\n")
    _commit_all(tmp_path, "initial")

    old_dir, new_dir = _render_dirs(tmp_path)
    (old_dir / "gone.txt").write_text("a\nb\n")
    (old_dir / "other.txt").write_text("old\n")
    (new_dir / "other.txt").write_text("new\n")

    success, _ = apply_patch(generate_diff(old_dir, new_dir), tmp_path)

    assert not success
    assert (tmp_path / "gone.txt").read_text() == "a\nb\nlocal\n"
    rej = (tmp_path / "gone.txt.rej").read_bytes()
    assert b"deleted file mode" in rej
    assert b"+++ /dev/null" in rej
    assert (tmp_path / "other.txt").read_text() == "new\n"


def test_apply_patch_ignores_deletion_of_file_already_removed(tmp_path: Path) -> None:
    """A file the user already deleted is in the state the template wants; other hunks still apply."""
    _init_repo(tmp_path)
    (tmp_path / "other.txt").write_text("old\n")
    _commit_all(tmp_path, "initial")

    old_dir, new_dir = _render_dirs(tmp_path)
    (old_dir / "gone.txt").write_text("a\n")
    (old_dir / "other.txt").write_text("old\n")
    (new_dir / "other.txt").write_text("new\n")

    success, stderr = apply_patch(generate_diff(old_dir, new_dir), tmp_path)

    assert success, stderr
    assert not (tmp_path / "gone.txt").exists()
    assert not (tmp_path / "gone.txt.rej").exists()
    assert (tmp_path / "other.txt").read_text() == "new\n"


def test_apply_patch_ignores_already_removed_file_alongside_conflict(tmp_path: Path) -> None:
    """Dropping an already-removed deletion must not hide a real conflict elsewhere."""
    _init_repo(tmp_path)
    (tmp_path / "other.txt").write_text("mine\n")
    _commit_all(tmp_path, "initial")

    old_dir, new_dir = _render_dirs(tmp_path)
    (old_dir / "gone.txt").write_text("a\n")
    (old_dir / "other.txt").write_text("old\n")
    (new_dir / "other.txt").write_text("new\n")

    success, _ = apply_patch(generate_diff(old_dir, new_dir), tmp_path)

    assert not success
    assert (tmp_path / "other.txt.rej").exists()
    assert not (tmp_path / "gone.txt.rej").exists()


def test_apply_patch_writes_rej_at_moved_path_when_template_deletes_modified_moved_file(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "x.txt").write_text("a\n")
    _commit_all(tmp_path, "initial")
    (tmp_path / "docs").mkdir()
    subprocess.run(["git", "mv", "x.txt", "docs/x.txt"], cwd=tmp_path, check=True, capture_output=True)
    _commit_all(tmp_path, "move")
    (tmp_path / "docs" / "x.txt").write_text("a\nlocal\n")
    _commit_all(tmp_path, "edit")

    old_dir, new_dir = _render_dirs(tmp_path)
    (old_dir / "x.txt").write_text("a\n")
    (old_dir / "keep.txt").write_text("k\n")
    (new_dir / "keep.txt").write_text("k\n")

    success, _ = apply_patch(generate_diff(old_dir, new_dir), tmp_path)

    assert not success
    assert (tmp_path / "docs" / "x.txt").read_text() == "a\nlocal\n"
    assert b"deleted file mode" in (tmp_path / "docs" / "x.txt.rej").read_bytes()
