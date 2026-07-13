from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from rebake.cli import app

runner = CliRunner()


@pytest.mark.e2e
def test_reparametrize_no_changes(project_dir: Path) -> None:
    """Should exit early when no variables are changed."""
    with patch("rebake.reparametrize.prompt_all_variables", return_value={"project_name": "my-project"}):
        result = runner.invoke(app, ["reparametrize", str(project_dir)])

    assert result.exit_code == 0
    assert "No changes" in result.output


@pytest.mark.e2e
def test_reparametrize_updates_file_content(project_dir: Path) -> None:
    """Should update file content when project_name is changed."""
    with patch(
        "rebake.reparametrize.prompt_all_variables",
        return_value={"project_name": "new-project"},
    ):
        result = runner.invoke(app, ["reparametrize", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert "Patch applied" in result.output
    assert (project_dir / "README.md").read_text() == "# new-project\n"


@pytest.mark.e2e
def test_reparametrize_updates_config(project_dir: Path) -> None:
    """Should update context in rebake.yaml after reparametrize."""
    with patch(
        "rebake.reparametrize.prompt_all_variables",
        return_value={"project_name": "new-project"},
    ):
        runner.invoke(app, ["reparametrize", str(project_dir)])

    from rebake.config import RebakeConfig

    updated = RebakeConfig.load(project_dir).templates[0]
    assert updated.context["cookiecutter"]["project_name"] == "new-project"


@pytest.mark.e2e
def test_reparametrize_rejects_multi_template_without_data_loss(tmp_path: Path) -> None:
    """A multi-template repo must be rejected end-to-end, leaving every entry intact."""
    repo = tmp_path / "repo"
    repo.mkdir()
    rebake_yaml = repo / "rebake.yaml"
    rebake_yaml.write_text(
        "templates:\n"
        "  - template: https://example.com/a\n"
        "    commit: aaa\n"
        "    context:\n"
        "      cookiecutter:\n"
        "        project_name: a\n"
        "  - template: https://example.com/b\n"
        "    commit: bbb\n"
        "    target_directory: batch\n"
        "    context:\n"
        "      cookiecutter:\n"
        "        project_name: b\n"
    )
    for args in (
        ["init"],
        ["config", "user.email", "t@t"],
        ["config", "user.name", "t"],
        ["add", "."],
        ["commit", "-m", "init"],
    ):
        subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)
    before = rebake_yaml.read_text()

    result = runner.invoke(app, ["reparametrize", str(repo)])

    assert result.exit_code != 0
    # both template entries survive — no silent data loss
    assert rebake_yaml.read_text() == before
