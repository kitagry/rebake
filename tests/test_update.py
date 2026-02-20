import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from rebake.update import run_update


def make_project(tmp_path: Path, commit: str = "abc123") -> Path:
    (tmp_path / ".cruft.json").write_text(
        json.dumps({
            "template": "https://github.com/owner/template",
            "commit": commit,
            "context": {"cookiecutter": {"project_name": "my-project"}},
        })
    )
    (tmp_path / ".git").mkdir()  # gitリポジトリに見せかける
    return tmp_path


def test_update_aborts_if_working_tree_dirty(tmp_path):
    make_project(tmp_path)

    with patch("rebake.update.is_working_tree_clean", return_value=False):
        with pytest.raises(RuntimeError, match="uncommitted changes"):
            run_update(tmp_path)


def test_update_detects_new_variables_and_prompts(tmp_path):
    project_dir = make_project(tmp_path, commit="abc123")

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.get_template_head_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={"license": "MIT"}),
        patch("rebake.update.prompt_new_variables", return_value={"license": "Apache-2.0"}) as mock_prompt,
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=True),
    ):
        run_update(project_dir)

    mock_prompt.assert_called_once_with({"license": "MIT"})


def test_update_saves_new_commit_and_context(tmp_path):
    project_dir = make_project(tmp_path, commit="abc123")

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.get_template_head_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={"license": "MIT"}),
        patch("rebake.update.prompt_new_variables", return_value={"license": "Apache-2.0"}),
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=True),
    ):
        run_update(project_dir)

    from rebake.config import CruftConfig
    updated = CruftConfig.load(project_dir)
    assert updated.commit == "def456"
    assert updated.context["cookiecutter"]["license"] == "Apache-2.0"


def test_update_skips_prompt_when_no_new_variables(tmp_path):
    project_dir = make_project(tmp_path, commit="abc123")

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.get_template_head_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables") as mock_prompt,
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=True),
    ):
        run_update(project_dir)

    mock_prompt.assert_not_called()


def test_update_applies_patch_with_three_way(tmp_path):
    project_dir = make_project(tmp_path, commit="abc123")
    patch_content = "some diff content"

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.get_template_head_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value=patch_content),
        patch("rebake.update.apply_patch", return_value=True) as mock_apply,
    ):
        run_update(project_dir)

    mock_apply.assert_called_once_with(patch_content, project_dir, three_way=True)
