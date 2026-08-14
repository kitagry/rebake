from __future__ import annotations

from unittest.mock import patch

import pytest
import yaml

from rebake.create import _parse_add_spec, run_create


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("https://github.com/o/t", ("https://github.com/o/t", ".")),  # bare → root
        ("https://github.com/o/t=api", ("https://github.com/o/t", "api")),
        ("./local/template=batch", ("./local/template", "batch")),
        # A nested target is fine; run_add creates intermediate directories.
        ("https://github.com/o/t=deep/nested/dir", ("https://github.com/o/t", "deep/nested/dir")),
        # rpartition splits on the LAST '='; a template URL containing '=' still parses.
        ("https://host/t?ref=v1=api", ("https://host/t?ref=v1", "api")),
    ],
)
def test_parse_add_spec(spec, expected):
    assert _parse_add_spec(spec) == expected


@pytest.mark.parametrize("bad_spec", ["", "=api", "template="])
def test_parse_add_spec_rejects_empty_side(bad_spec):
    with pytest.raises(ValueError):
        _parse_add_spec(bad_spec)


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


def test_create_with_additional_appends_entries_in_order(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    # Real rendered dirs for the additional templates; run_add copytree's them.
    render_b = tmp_path / "render_b"
    render_b.mkdir()
    (render_b / "b.txt").write_text("b\n")
    render_c = tmp_path / "render_c"
    render_c.mkdir()
    (render_c / "c.txt").write_text("c\n")

    with (
        patch("rebake.create.resolve_template_commit", side_effect=["aaa", "bbb", "ccc"]),
        patch(
            "rebake.create.cookiecutter_interactive",
            side_effect=[
                (str(rendered_project), {"project_name": "my-project"}),
                (str(render_b), {"project_name": "proj-b"}),
                (str(render_c), {"project_name": "proj-c"}),
            ],
        ),
    ):
        project = run_create(
            "https://github.com/owner/primary",
            output_dir=output_dir,
            additional=[
                "https://github.com/owner/b=batch",
                "https://github.com/owner/c=api",
            ],
        )

    assert project == rendered_project
    # Additional templates land in their sub-directories with the wrapper stripped.
    assert (rendered_project / "batch" / "b.txt").read_text() == "b\n"
    assert (rendered_project / "api" / "c.txt").read_text() == "c\n"

    templates = yaml.safe_load((rendered_project / "rebake.yaml").read_text())["templates"]
    assert [t["template"] for t in templates] == [
        "https://github.com/owner/primary",
        "https://github.com/owner/b",
        "https://github.com/owner/c",
    ]
    assert [t["commit"] for t in templates] == ["aaa", "bbb", "ccc"]
    # primary omits target_directory ("."); additional links record theirs.
    assert "target_directory" not in templates[0]
    assert templates[1]["target_directory"] == "batch"
    assert templates[2]["target_directory"] == "api"


def test_create_bare_add_spec_renders_at_root(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered_project = output_dir / "my-project"
    rendered_project.mkdir()

    render_b = tmp_path / "render_b"
    render_b.mkdir()
    (render_b / "b.txt").write_text("b\n")

    with (
        patch("rebake.create.resolve_template_commit", side_effect=["aaa", "bbb"]),
        patch(
            "rebake.create.cookiecutter_interactive",
            side_effect=[
                (str(rendered_project), {"project_name": "my-project"}),
                (str(render_b), {"project_name": "proj-b"}),
            ],
        ),
    ):
        run_create(
            "https://github.com/owner/primary",
            output_dir=output_dir,
            additional=["https://github.com/owner/b"],  # no =TARGET → repo root
        )

    # A bare spec renders at the root, so its files land directly in the project.
    assert (rendered_project / "b.txt").read_text() == "b\n"
    templates = yaml.safe_load((rendered_project / "rebake.yaml").read_text())["templates"]
    assert [t["template"] for t in templates] == [
        "https://github.com/owner/primary",
        "https://github.com/owner/b",
    ]
    # Root target is the default, so "." is omitted from both entries.
    assert all("target_directory" not in t for t in templates)


@pytest.mark.parametrize("bad_target", ["../escape", "/abs/path", "a/../../b"])
def test_create_rejects_unsafe_target(tmp_path, bad_target):
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with (
        patch("rebake.create.resolve_template_commit") as mock_commit,
        patch("rebake.create.cookiecutter_interactive") as mock_cc,
        pytest.raises(ValueError),
    ):
        run_create(
            "https://github.com/owner/primary",
            output_dir=output_dir,
            additional=[f"https://github.com/owner/b={bad_target}"],
        )

    # The guard fires before anything is rendered.
    mock_commit.assert_not_called()
    mock_cc.assert_not_called()
    assert list(output_dir.iterdir()) == []
