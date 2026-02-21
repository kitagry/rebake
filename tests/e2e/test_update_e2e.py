from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rebake.cli import app

runner = CliRunner()


@pytest.mark.e2e
def test_update_no_changes(project_dir: Path) -> None:
    result = runner.invoke(app, ["update", str(project_dir)])
    assert result.exit_code == 0
    assert "No changes" in result.output


@pytest.mark.e2e
def test_update_applies_new_file(project_dir: Path, template_repo: Path) -> None:
    new_file = template_repo / "{{cookiecutter.project_name}}" / "newfile.txt"
    new_file.write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=template_repo, check=True)
    subprocess.run(["git", "commit", "-m", "add newfile.txt"], cwd=template_repo, check=True)

    result = runner.invoke(app, ["update", str(project_dir)])
    assert result.exit_code == 0
    assert (project_dir / "newfile.txt").read_text() == "hello\n"


@pytest.mark.e2e
def test_update_removes_deleted_file(project_dir: Path, template_repo: Path) -> None:
    # Keep README.md so the template project directory is not left empty
    (template_repo / "{{cookiecutter.project_name}}" / "CONTRIBUTING.md").unlink()
    subprocess.run(["git", "add", "."], cwd=template_repo, check=True)
    subprocess.run(["git", "commit", "-m", "remove CONTRIBUTING.md"], cwd=template_repo, check=True)

    result = runner.invoke(app, ["update", str(project_dir)])
    assert result.exit_code == 0
    assert not (project_dir / "CONTRIBUTING.md").exists()
