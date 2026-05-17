from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml

from rebake.create import run_create
from rebake.utils.recipe import Recipe


def test_create_renders_template_and_writes_rebake_yaml(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    with (
        patch("rebake.create.get_template_head_commit", return_value="abc123"),
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project"}, Recipe()),
        ) as mock_cc,
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir)

    mock_cc.assert_called_once()
    rebake_yaml = rendered_project / "rebake.yaml"
    assert rebake_yaml.exists()
    data = yaml.safe_load(rebake_yaml.read_text())
    assert data["template"] == "https://github.com/owner/template"
    assert data["commit"] == "abc123"
    assert "cookiecutter" in data["context"]


def test_create_uses_checkout(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    with (
        patch("rebake.create.get_template_head_commit", return_value="def456") as mock_commit,
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project"}, Recipe()),
        ),
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir, checkout="v1.0")

    mock_commit.assert_called_once_with("https://github.com/owner/template", checkout="v1.0")
    data = yaml.safe_load((rendered_project / "rebake.yaml").read_text())
    assert data["checkout"] == "v1.0"


def test_create_saves_context_from_cookiecutter(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    with (
        patch("rebake.create.get_template_head_commit", return_value="abc123"),
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project", "author": "me"}, Recipe()),
        ),
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir)

    data = yaml.safe_load((rendered_project / "rebake.yaml").read_text())
    assert data["context"]["cookiecutter"]["project_name"] == "my-project"
    assert data["context"]["cookiecutter"]["author"] == "me"


def test_create_without_checkout_omits_field(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    with (
        patch("rebake.create.get_template_head_commit", return_value="abc123"),
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project"}, Recipe()),
        ),
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir)

    data = yaml.safe_load((rendered_project / "rebake.yaml").read_text())
    assert "checkout" not in data


def test_create_writes_recipe_hooks_into_rebake_yaml(tmp_path: Path) -> None:
    """Recipe hooks returned by cookiecutter_interactive land in rebake.yaml.hooks."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    recipe = Recipe(
        hooks={
            "pre-update": ["echo pre"],
            "post-update": ["echo post"],
        }
    )

    with (
        patch("rebake.create.get_template_head_commit", return_value="abc123"),
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project"}, recipe),
        ),
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir)

    data = yaml.safe_load((rendered_project / "rebake.yaml").read_text())
    assert data["hooks"] == {
        "pre-update": ["echo pre"],
        "post-update": ["echo post"],
    }


def test_create_without_recipe_hooks_omits_hooks_field(tmp_path: Path) -> None:
    """An empty Recipe must not produce an empty `hooks: {}` block in rebake.yaml."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    with (
        patch("rebake.create.get_template_head_commit", return_value="abc123"),
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project"}, Recipe()),
        ),
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir)

    data = yaml.safe_load((rendered_project / "rebake.yaml").read_text())
    assert "hooks" not in data
