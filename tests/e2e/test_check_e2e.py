from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rebake.cli import app

runner = CliRunner()


@pytest.mark.e2e
def test_check_up_to_date(project_dir: Path) -> None:
    result = runner.invoke(app, ["check", str(project_dir)])
    assert result.exit_code == 0


@pytest.mark.e2e
def test_check_outdated(project_dir: Path, template_repo: Path) -> None:
    (template_repo / "cookiecutter.json").write_text(json.dumps({"project_name": "my-project", "license": "MIT"}))
    subprocess.run(["git", "add", "."], cwd=template_repo, check=True)
    subprocess.run(["git", "commit", "-m", "add license var"], cwd=template_repo, check=True)

    result = runner.invoke(app, ["check", str(project_dir)])
    assert result.exit_code == 1


@pytest.mark.e2e
def test_check_missing_cruft_json(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 2
