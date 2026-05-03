from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from rebake.cli import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"

runner = CliRunner()


def _make_template_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "template"
    shutil.copytree(FIXTURES_DIR / "simple_template", repo)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
    return repo


@pytest.mark.e2e
def test_create_generates_project_and_rebake_yaml(tmp_path: Path) -> None:
    template_repo = _make_template_repo(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = runner.invoke(
        app,
        ["create", str(template_repo), "--output-dir", str(output_dir)],
        input="my-project\n",  # cookiecutter プロンプトへの回答
    )

    assert result.exit_code == 0, result.output
    project_dir = output_dir / "my-project"
    assert project_dir.is_dir()

    rebake_yaml = project_dir / "rebake.yaml"
    assert rebake_yaml.exists()
    data = yaml.safe_load(rebake_yaml.read_text())
    assert data["template"] == str(template_repo)
    assert "commit" in data
    assert len(data["commit"]) == 40  # SHA-1 full hash
    assert data["context"]["cookiecutter"]["project_name"] == "my-project"


@pytest.mark.e2e
def test_create_with_checkout(tmp_path: Path) -> None:
    template_repo = _make_template_repo(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = runner.invoke(
        app,
        ["create", str(template_repo), "--output-dir", str(output_dir), "--checkout", "main"],
        input="my-project\n",
    )

    assert result.exit_code == 0, result.output
    data = yaml.safe_load((output_dir / "my-project" / "rebake.yaml").read_text())
    assert data["checkout"] == "main"
