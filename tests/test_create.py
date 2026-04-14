from __future__ import annotations

import json
from unittest.mock import patch

from rebake.create import run_create


def test_create_renders_template_and_writes_cruft_json(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    with (
        patch("rebake.create.get_template_head_commit", return_value="abc123"),
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project"}),
        ) as mock_cc,
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir)

    mock_cc.assert_called_once()
    cruft_json = rendered_project / ".cruft.json"
    assert cruft_json.exists()
    data = json.loads(cruft_json.read_text())
    assert data["template"] == "https://github.com/owner/template"
    assert data["commit"] == "abc123"
    assert "cookiecutter" in data["context"]


def test_create_uses_checkout(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    with (
        patch("rebake.create.get_template_head_commit", return_value="def456") as mock_commit,
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project"}),
        ),
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir, checkout="v1.0")

    mock_commit.assert_called_once_with("https://github.com/owner/template", checkout="v1.0")
    cruft_json = rendered_project / ".cruft.json"
    data = json.loads(cruft_json.read_text())
    assert data["checkout"] == "v1.0"


def test_create_saves_context_from_cookiecutter(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    with (
        patch("rebake.create.get_template_head_commit", return_value="abc123"),
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project", "author": "me"}),
        ),
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir)

    data = json.loads((rendered_project / ".cruft.json").read_text())
    assert data["context"]["cookiecutter"]["project_name"] == "my-project"
    assert data["context"]["cookiecutter"]["author"] == "me"


def test_create_without_checkout_omits_field(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    with (
        patch("rebake.create.get_template_head_commit", return_value="abc123"),
        patch(
            "rebake.create.cookiecutter_interactive",
            return_value=(str(rendered_project), {"project_name": "my-project"}),
        ),
    ):
        run_create("https://github.com/owner/template", output_dir=output_dir)

    data = json.loads((rendered_project / ".cruft.json").read_text())
    assert "checkout" not in data
