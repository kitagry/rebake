import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from rebake.config import RebakeConfig
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


def make_multi_project(tmp_path: Path, *, named: bool = True) -> Path:
    entry_a = {"template": "https://x/a", "commit": "aaa", "context": {"cookiecutter": {"x": "1"}}}
    entry_b = {
        "template": "https://x/b",
        "commit": "bbb",
        "target_directory": "batch",
        "context": {"cookiecutter": {"y": "2"}},
    }
    if named:
        entry_a["name"] = "a"
        entry_b["name"] = "b"
    (tmp_path / "rebake.yaml").write_text(yaml.dump({"templates": [entry_a, entry_b]}))
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

    updated = RebakeConfig.load(project_dir).templates[0]
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


def test_reparametrize_loops_over_all_templates(tmp_path):
    project_dir = make_multi_project(tmp_path)

    with (
        patch("rebake.reparametrize.is_working_tree_clean", return_value=True),
        patch(
            "rebake.reparametrize.prompt_all_variables", side_effect=[{"x": "changed"}, {"y": "changed"}]
        ) as mock_prompt,
        patch("rebake.reparametrize.clone_at_commit"),
        patch("rebake.reparametrize.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.reparametrize.generate_diff", return_value=b"diff"),
        patch("rebake.reparametrize.apply_patch", return_value=(True, "")) as mock_apply,
    ):
        run_reparametrize(project_dir)

    assert mock_prompt.call_count == 2
    assert mock_apply.call_count == 2


def test_reparametrize_name_targets_single_entry(tmp_path):
    project_dir = make_multi_project(tmp_path)

    with (
        patch("rebake.reparametrize.is_working_tree_clean", return_value=True),
        patch("rebake.reparametrize.prompt_all_variables", return_value={"y": "changed"}) as mock_prompt,
        patch("rebake.reparametrize.clone_at_commit"),
        patch("rebake.reparametrize.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.reparametrize.generate_diff", return_value=b""),
        patch("rebake.reparametrize.apply_patch", return_value=(True, "")),
    ):
        run_reparametrize(project_dir, name="b")

    mock_prompt.assert_called_once()
    templates = {e.name: e for e in RebakeConfig.load(project_dir).templates}
    assert templates["b"].context["cookiecutter"] == {"y": "changed"}
    assert templates["a"].context["cookiecutter"] == {"x": "1"}


def test_reparametrize_unknown_name_raises_and_does_not_touch_config(tmp_path):
    project_dir = make_multi_project(tmp_path)
    rebake_yaml = project_dir / "rebake.yaml"
    before = rebake_yaml.read_text()

    with patch("rebake.reparametrize.is_working_tree_clean", return_value=True):
        with pytest.raises(RuntimeError) as exc:
            run_reparametrize(project_dir, name="nope")

    assert "No template link named 'nope'" in str(exc.value)
    assert "Named links: a, b" in str(exc.value)
    assert rebake_yaml.read_text() == before


def test_reparametrize_name_on_unnamed_only_lists_no_named_links(tmp_path):
    project_dir = make_multi_project(tmp_path, named=False)

    with patch("rebake.reparametrize.is_working_tree_clean", return_value=True):
        with pytest.raises(RuntimeError, match=r"\(no named links\)"):
            run_reparametrize(project_dir, name="a")


def test_reparametrize_per_entry_no_changes_continues(tmp_path):
    project_dir = make_multi_project(tmp_path)

    with (
        patch("rebake.reparametrize.is_working_tree_clean", return_value=True),
        # entry "a" unchanged (same as its stored context), entry "b" changed
        patch("rebake.reparametrize.prompt_all_variables", side_effect=[{"x": "1"}, {"y": "changed"}]),
        patch("rebake.reparametrize.clone_at_commit") as mock_clone,
        patch("rebake.reparametrize.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.reparametrize.generate_diff", return_value=b"diff"),
        patch("rebake.reparametrize.apply_patch", return_value=(True, "")) as mock_apply,
    ):
        run_reparametrize(project_dir)

    # only entry "b" reaches clone/apply; "a" returns early without aborting the loop
    mock_clone.assert_called_once()
    mock_apply.assert_called_once()
    templates = {e.name: e for e in RebakeConfig.load(project_dir).templates}
    assert templates["a"].context["cookiecutter"] == {"x": "1"}
    assert templates["b"].context["cookiecutter"] == {"y": "changed"}
