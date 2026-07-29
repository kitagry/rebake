from __future__ import annotations

from unittest.mock import patch

import yaml

from rebake.create import run_create


def test_create_renders_template_and_writes_rebake_yaml(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    with (
        patch("rebake.create.resolve_template_commit", return_value="abc123"),
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project"}),
        ) as mock_cc,
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir)

    mock_cc.assert_called_once()
    rebake_yaml = rendered_project / "rebake.yaml"
    assert rebake_yaml.exists()
    entry = yaml.safe_load(rebake_yaml.read_text())["templates"][0]
    assert entry["template"] == "https://github.com/owner/template"
    assert entry["commit"] == "abc123"
    assert "cookiecutter" in entry["context"]


def test_create_uses_checkout(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    with (
        patch("rebake.create.resolve_template_commit", return_value="def456") as mock_commit,
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project"}),
        ),
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir, checkout="v1.0")

    mock_commit.assert_called_once_with("https://github.com/owner/template", checkout="v1.0")
    entry = yaml.safe_load((rendered_project / "rebake.yaml").read_text())["templates"][0]
    assert entry["checkout"] == "v1.0"


def test_create_saves_context_from_cookiecutter(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    with (
        patch("rebake.create.resolve_template_commit", return_value="abc123"),
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project", "author": "me"}),
        ),
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir)

    entry = yaml.safe_load((rendered_project / "rebake.yaml").read_text())["templates"][0]
    assert entry["context"]["cookiecutter"]["project_name"] == "my-project"
    assert entry["context"]["cookiecutter"]["author"] == "me"


def test_create_without_checkout_omits_field(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    with (
        patch("rebake.create.resolve_template_commit", return_value="abc123"),
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project"}),
        ),
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir)

    entry = yaml.safe_load((rendered_project / "rebake.yaml").read_text())["templates"][0]
    assert "checkout" not in entry
