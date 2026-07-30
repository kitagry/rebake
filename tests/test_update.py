import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from rebake.update import run_update


def make_project(tmp_path: Path, commit: str = "abc123") -> Path:
    (tmp_path / ".cruft.json").write_text(
        json.dumps(
            {
                "template": "https://github.com/owner/template",
                "commit": commit,
                "context": {"cookiecutter": {"project_name": "my-project"}},
            }
        )
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
        patch("rebake.update.resolve_template_commit", return_value="def456"),
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
        patch("rebake.update.resolve_template_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={"license": "MIT"}),
        patch("rebake.update.prompt_new_variables", return_value={"license": "Apache-2.0"}),
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=True),
    ):
        run_update(project_dir)

    from rebake.config import RebakeConfig

    updated = RebakeConfig.load(project_dir).templates[0]
    assert updated.commit == "def456"
    assert updated.context["cookiecutter"]["license"] == "Apache-2.0"


def test_update_skips_prompt_when_no_new_variables(tmp_path):
    project_dir = make_project(tmp_path, commit="abc123")

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables") as mock_prompt,
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=True),
    ):
        run_update(project_dir)

    mock_prompt.assert_not_called()


def test_update_applies_patch(tmp_path):
    project_dir = make_project(tmp_path, commit="abc123")
    patch_content = "some diff content"

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value=patch_content),
        patch("rebake.update.apply_patch", return_value=(True, "")) as mock_apply,
    ):
        run_update(project_dir)

    mock_apply.assert_called_once_with(patch_content, project_dir.resolve())


def test_update_passes_allow_untracked_files_flag_to_git_check(tmp_path):
    """The allow_untracked_files flag must be forwarded to is_working_tree_clean."""
    project_dir = make_project(tmp_path)

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True) as mock_clean,
        patch("rebake.update.resolve_template_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=(True, "")),
    ):
        run_update(project_dir, allow_untracked_files=True)

    mock_clean.assert_called_once_with(project_dir.resolve(), allow_untracked_files=True)


def test_update_quiet_mode_raises_when_new_variables(tmp_path):
    """In quiet mode, raise RuntimeError when new variables are detected."""
    project_dir = make_project(tmp_path)

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={"license": "MIT"}),
        patch("rebake.update.prompt_new_variables") as mock_prompt,
        patch("rebake.update.generate_diff", return_value=""),
    ):
        with pytest.raises(RuntimeError, match="license"):
            run_update(project_dir, quiet=True)

    mock_prompt.assert_not_called()


def test_update_quiet_mode_succeeds_when_no_new_variables(tmp_path):
    """In quiet mode, succeed normally when there are no new variables."""
    project_dir = make_project(tmp_path)

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=(True, "")),
    ):
        run_update(project_dir, quiet=True)


def _patch_update_internals(**overrides):
    defaults = dict(
        is_working_tree_clean=True,
        resolve_template_commit="def456",
        clone_at_commit=None,
        render_template=Path("/tmp/rendered"),
        detect_new_variables={},
        prompt_new_variables=None,
        generate_diff="",
        apply_patch=(True, ""),
    )
    defaults.update(overrides)
    return defaults


def test_update_runs_pre_update_hook(tmp_path):
    project_dir = make_project(tmp_path)
    (tmp_path / "rebake.yaml").write_text(
        __import__("yaml").dump(
            {
                "template": "https://github.com/owner/template",
                "commit": "abc123",
                "context": {"cookiecutter": {"project_name": "my-project"}},
                "hooks": {"pre-update": ["echo pre"]},
            }
        )
    )

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=(True, "")),
        patch("rebake.update.run_hooks") as mock_hooks,
    ):
        run_update(project_dir)

    calls = [c.args[0] for c in mock_hooks.call_args_list]
    assert "pre-update" in calls


def test_update_runs_post_update_hook(tmp_path):
    project_dir = make_project(tmp_path)
    (tmp_path / "rebake.yaml").write_text(
        __import__("yaml").dump(
            {
                "template": "https://github.com/owner/template",
                "commit": "abc123",
                "context": {"cookiecutter": {"project_name": "my-project"}},
                "hooks": {"post-update": ["echo post"]},
            }
        )
    )

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=(True, "")),
        patch("rebake.update.run_hooks") as mock_hooks,
    ):
        run_update(project_dir)

    calls = [c.args[0] for c in mock_hooks.call_args_list]
    assert "post-update" in calls


def test_update_pre_hook_runs_before_patch(tmp_path):
    """pre-update hook must be called before apply_patch."""
    project_dir = make_project(tmp_path)
    call_order = []

    def record_hook(event, *args, **kwargs):
        call_order.append(f"hook:{event}")

    def record_apply(patch_content, path):
        call_order.append("apply_patch")
        return (True, "")

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value="diff content"),
        patch("rebake.update.apply_patch", side_effect=record_apply),
        patch("rebake.update.run_hooks", side_effect=record_hook),
    ):
        run_update(project_dir)

    pre_idx = call_order.index("hook:pre-update")
    apply_idx = call_order.index("apply_patch")
    assert pre_idx < apply_idx


def test_update_post_hook_runs_after_config_save(tmp_path):
    """post-update hook must be called after config.save."""
    project_dir = make_project(tmp_path)
    call_order = []

    def record_save(path):
        call_order.append("save")

    def record_hook(event, *args, **kwargs):
        call_order.append(f"hook:{event}")

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=(True, "")),
        patch("rebake.config.RebakeConfig.save", side_effect=record_save),
        patch("rebake.update.run_hooks", side_effect=record_hook),
    ):
        run_update(project_dir)

    save_idx = call_order.index("save")
    post_idx = call_order.index("hook:post-update")
    assert save_idx < post_idx


def test_update_with_checkout_advances_to_that_ref(tmp_path):
    """When checkout is given, the project is updated to that ref's commit, not HEAD."""
    project_dir = make_project(tmp_path)
    head_ref = "commit1_as_head"
    midway_ref = "commit2_as_midway"

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", return_value=head_ref) as mock_resolve,
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=(True, "")),
    ):
        run_update(project_dir, checkout=midway_ref)

    mock_resolve.assert_called_once_with("https://github.com/owner/template", checkout=midway_ref)

    from rebake.config import RebakeConfig

    updated = RebakeConfig.load(project_dir).templates[0]
    assert updated.checkout == midway_ref


def test_update_aborts_if_pre_hook_fails(tmp_path):
    project_dir = make_project(tmp_path)

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value="diff"),
        patch("rebake.update.apply_patch", return_value=(True, "")) as mock_apply,
        patch(
            "rebake.update.run_hooks",
            side_effect=lambda event, *a, **kw: (
                (_ for _ in ()).throw(RuntimeError("hook failed")) if event == "pre-update" else None
            ),
        ),
    ):
        with pytest.raises(RuntimeError, match="hook failed"):
            run_update(project_dir)

    mock_apply.assert_not_called()


def test_update_aborts_if_post_hook_fails(tmp_path):
    project_dir = make_project(tmp_path)

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", return_value="def456"),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=(True, "")),
        patch(
            "rebake.update.run_hooks",
            side_effect=lambda event, *a, **kw: (
                (_ for _ in ()).throw(RuntimeError("post hook failed")) if event == "post-update" else None
            ),
        ),
    ):
        with pytest.raises(RuntimeError, match="post hook failed"):
            run_update(project_dir)


def make_multi_project(tmp_path: Path) -> Path:
    (tmp_path / "rebake.yaml").write_text(
        yaml.dump(
            {
                "templates": [
                    {
                        "template": "https://x/common",
                        "commit": "aaa",
                        "name": "common",
                        "context": {"cookiecutter": {}},
                    },
                    {
                        "template": "https://x/go",
                        "commit": "bbb",
                        "name": "go",
                        "target_directory": "api",
                        "context": {"cookiecutter": {}},
                    },
                ]
            }
        )
    )
    (tmp_path / ".git").mkdir()
    return tmp_path


def test_update_checkout_targets_named_entry_in_multi(tmp_path):
    project_dir = make_multi_project(tmp_path)
    seen: dict[str, str | None] = {}

    def fake_head(template, checkout=None):
        seen[template] = checkout
        return {"https://x/common": "aaa", "https://x/go": "bbb"}[template]

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", side_effect=fake_head),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=(True, "")),
    ):
        run_update(project_dir, checkout="go@main")

    # only the `go` link's checkout is overridden
    assert seen["https://x/go"] == "main"
    assert seen["https://x/common"] is None

    saved = yaml.safe_load((project_dir / "rebake.yaml").read_text())
    go = next(entry for entry in saved["templates"] if entry["name"] == "go")
    assert go["checkout"] == "main"
    common = next(entry for entry in saved["templates"] if entry["name"] == "common")
    assert "checkout" not in common


def test_update_checkout_without_name_on_multi_raises(tmp_path):
    project_dir = make_multi_project(tmp_path)

    with patch("rebake.update.is_working_tree_clean", return_value=True):
        with pytest.raises(RuntimeError, match="ambiguous"):
            run_update(project_dir, checkout="main")


def test_update_checkout_empty_ref_on_multi_raises(tmp_path):
    project_dir = make_multi_project(tmp_path)

    with patch("rebake.update.is_working_tree_clean", return_value=True):
        with pytest.raises(RuntimeError, match="ambiguous"):
            run_update(project_dir, checkout="go@")


def test_update_checkout_unknown_name_on_multi_raises(tmp_path):
    project_dir = make_multi_project(tmp_path)

    with patch("rebake.update.is_working_tree_clean", return_value=True):
        with pytest.raises(RuntimeError, match="nope"):
            run_update(project_dir, checkout="nope@main")


def test_update_names_scopes_to_selected_entry(tmp_path):
    project_dir = make_multi_project(tmp_path)
    processed: list[str] = []

    def fake_head(template, checkout=None):
        processed.append(template)
        return {"https://x/common": "aaa", "https://x/go": "newgo"}[template]

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", side_effect=fake_head),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=(True, "")),
    ):
        run_update(project_dir, names=["go"])

    # only the `go` link is touched; `common` is never even resolved
    assert processed == ["https://x/go"]
    saved = {e["name"]: e for e in yaml.safe_load((project_dir / "rebake.yaml").read_text())["templates"]}
    assert saved["go"]["commit"] == "newgo"
    assert saved["common"]["commit"] == "aaa"


def test_update_names_unknown_raises(tmp_path):
    project_dir = make_multi_project(tmp_path)

    with patch("rebake.update.is_working_tree_clean", return_value=True):
        with pytest.raises(RuntimeError, match="nope"):
            run_update(project_dir, names=["nope"])


def test_update_name_and_checkout_same_link_composes(tmp_path):
    project_dir = make_multi_project(tmp_path)
    processed: list[tuple[str, str | None]] = []

    def fake_head(template, checkout=None):
        processed.append((template, checkout))
        return {"https://x/common": "aaa", "https://x/go": "newgo"}[template]

    with (
        patch("rebake.update.is_working_tree_clean", return_value=True),
        patch("rebake.update.resolve_template_commit", side_effect=fake_head),
        patch("rebake.update.clone_at_commit"),
        patch("rebake.update.render_template", return_value=Path("/tmp/rendered")),
        patch("rebake.update.detect_new_variables", return_value={}),
        patch("rebake.update.prompt_new_variables"),
        patch("rebake.update.generate_diff", return_value=""),
        patch("rebake.update.apply_patch", return_value=(True, "")),
    ):
        run_update(project_dir, names=["go"], checkout="go@main")

    # `--name go --checkout go@main` compose: only `go` runs, at ref `main`
    assert processed == [("https://x/go", "main")]


def test_update_name_and_checkout_different_links_raises(tmp_path):
    project_dir = make_multi_project(tmp_path)

    with patch("rebake.update.is_working_tree_clean", return_value=True):
        with pytest.raises(RuntimeError, match="does not select"):
            run_update(project_dir, names=["common"], checkout="go@main")
