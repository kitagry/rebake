import json
from pathlib import Path
from unittest.mock import patch

import pytest

from rebake.reparametrize import run_reparametrize


def make_project(tmp_path: Path, commit: str = "abc123") -> Path:
    (tmp_path / ".cruft.json").write_text(
        json.dumps(
            {
                "template": "https://github.com/owner/template",
                "commit": commit,
                "context": {"cookiecutter": {"project_name": "my-project", "author": "Alice"}},
            }
        )
    )
    (tmp_path / ".git").mkdir()
    return tmp_path


def test_reparametrize_aborts_if_working_tree_dirty(tmp_path):
    make_project(tmp_path)

    with patch("rebake.reparametrize.is_working_tree_clean", return_value=False):
        with pytest.raises(RuntimeError, match="uncommitted changes"):
            run_reparametrize(tmp_path)


def test_reparametrize_early_exit_when_no_changes(tmp_path):
    project_dir = make_project(tmp_path)
    old_context = {"project_name": "my-project", "author": "Alice"}

    with (
        patch("rebake.reparametrize.is_working_tree_clean", return_value=True),
        patch("rebake.reparametrize.prompt_all_variables", return_value=old_context) as mock_prompt,
        patch("rebake.reparametrize.clone_at_commit") as mock_clone,
    ):
        run_reparametrize(project_dir)

    mock_prompt.assert_called_once_with(old_context)
    mock_clone.assert_not_called()


def test_reparametrize_applies_patch_when_context_changed(tmp_path):
    project_dir = make_project(tmp_path)
    new_context = {"project_name": "my-project", "author": "Bob"}
    patch_content = b"some diff content"

    with (
        patch("rebake.reparametrize.is_working_tree_clean", return_value=True),
        patch("rebake.reparametrize.prompt_all_variables", return_value=new_context),
        patch("rebake.reparametrize.clone_at_commit"),
        patch("rebake.reparametrize.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.reparametrize.generate_diff", return_value=patch_content),
        patch("rebake.reparametrize.apply_patch", return_value=(True, "")) as mock_apply,
    ):
        run_reparametrize(project_dir)

    mock_apply.assert_called_once_with(patch_content, project_dir.resolve())


def test_reparametrize_saves_new_context(tmp_path):
    project_dir = make_project(tmp_path)
    new_context = {"project_name": "my-project", "author": "Bob"}

    with (
        patch("rebake.reparametrize.is_working_tree_clean", return_value=True),
        patch("rebake.reparametrize.prompt_all_variables", return_value=new_context),
        patch("rebake.reparametrize.clone_at_commit"),
        patch("rebake.reparametrize.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.reparametrize.generate_diff", return_value=b""),
        patch("rebake.reparametrize.apply_patch", return_value=(True, "")),
    ):
        run_reparametrize(project_dir)

    from rebake.config import CruftConfig

    updated = CruftConfig.load(project_dir)
    assert updated.context["cookiecutter"]["author"] == "Bob"
    # commit hash は変わらない
    assert updated.commit == "abc123"


def test_reparametrize_skips_apply_when_no_diff(tmp_path):
    project_dir = make_project(tmp_path)
    new_context = {"project_name": "my-project", "author": "Bob"}

    with (
        patch("rebake.reparametrize.is_working_tree_clean", return_value=True),
        patch("rebake.reparametrize.prompt_all_variables", return_value=new_context),
        patch("rebake.reparametrize.clone_at_commit"),
        patch("rebake.reparametrize.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.reparametrize.generate_diff", return_value=b""),
        patch("rebake.reparametrize.apply_patch") as mock_apply,
    ):
        run_reparametrize(project_dir)

    mock_apply.assert_not_called()


def test_reparametrize_passes_allow_untracked_files_flag(tmp_path):
    make_project(tmp_path)

    with (
        patch("rebake.reparametrize.is_working_tree_clean", return_value=True) as mock_clean,
        patch(
            "rebake.reparametrize.prompt_all_variables", return_value={"project_name": "my-project", "author": "Alice"}
        ),
    ):
        run_reparametrize(tmp_path, allow_untracked_files=True)

    mock_clean.assert_called_once_with(tmp_path.resolve(), allow_untracked_files=True)
