from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from rebake.cli import app

runner = CliRunner()


@pytest.mark.e2e
def test_reparametrize_no_changes(project_dir: Path) -> None:
    """変数を変更しない場合は early exit する。"""
    with patch("rebake.reparametrize.prompt_all_variables", return_value={"project_name": "my-project"}):
        result = runner.invoke(app, ["reparametrize", str(project_dir)])

    assert result.exit_code == 0
    assert "No changes" in result.output


@pytest.mark.e2e
def test_reparametrize_updates_file_content(project_dir: Path) -> None:
    """project_name を変更するとファイル内容が更新される。"""
    with patch(
        "rebake.reparametrize.prompt_all_variables",
        return_value={"project_name": "new-project"},
    ):
        result = runner.invoke(app, ["reparametrize", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert "Patch applied" in result.output
    assert (project_dir / "README.md").read_text() == "# new-project\n"


@pytest.mark.e2e
def test_reparametrize_updates_cruft_json(project_dir: Path) -> None:
    """変更後に .cruft.json の context が更新される。"""
    with patch(
        "rebake.reparametrize.prompt_all_variables",
        return_value={"project_name": "new-project"},
    ):
        runner.invoke(app, ["reparametrize", str(project_dir)])

    from rebake.config import CruftConfig

    updated = CruftConfig.load(project_dir)
    assert updated.context["cookiecutter"]["project_name"] == "new-project"
