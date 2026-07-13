from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from cookiecutter.main import cookiecutter
from typer.testing import CliRunner

from rebake.cli import app
from rebake.config import RebakeConfig

FIXTURES_DIR = Path(__file__).parent / "fixtures"

runner = CliRunner()


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True)


def _head_commit(repo: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _make_template_repo(dest: Path) -> Path:
    shutil.copytree(FIXTURES_DIR / "simple_template", dest)
    _git(["init", "-b", "main"], dest)
    _git(["config", "user.email", "test@test.com"], dest)
    _git(["config", "user.name", "Test"], dest)
    _git(["add", "."], dest)
    _git(["commit", "-m", "init"], dest)
    return dest


def _render_into(template: Path, target: Path, project_name: str, tmp: Path) -> None:
    """Render a template and place its contents directly under target (wrapper stripped)."""
    out = tmp / f"render_{project_name}"
    out.mkdir()
    rendered = cookiecutter(
        str(template), no_input=True, extra_context={"project_name": project_name}, output_dir=str(out)
    )
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(rendered, target, dirs_exist_ok=True)


def _setup_multi_repo(tmp_path: Path, *, named: bool) -> Path:
    """Build a two-template repo: template_a at the root, template_b under batch/."""
    template_a = _make_template_repo(tmp_path / "template_a")
    template_b = _make_template_repo(tmp_path / "template_b")
    repo = tmp_path / "repo"
    repo.mkdir()
    _render_into(template_a, repo, "proj-a", tmp_path)
    _render_into(template_b, repo / "batch", "proj-b", tmp_path)

    entry_a = {
        "template": str(template_a),
        "commit": _head_commit(template_a),
        "context": {"cookiecutter": {"project_name": "proj-a"}},
    }
    entry_b = {
        "template": str(template_b),
        "commit": _head_commit(template_b),
        "target_directory": "batch",
        "context": {"cookiecutter": {"project_name": "proj-b"}},
    }
    if named:
        entry_a["name"] = "a"
        entry_b["name"] = "b"
    (repo / "rebake.yaml").write_text(yaml.dump({"templates": [entry_a, entry_b]}, allow_unicode=True, sort_keys=False))

    _git(["init"], repo)
    _git(["config", "user.email", "test@test.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    _git(["add", "."], repo)
    _git(["commit", "-m", "init repo"], repo)
    return repo


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

    updated = RebakeConfig.load(project_dir).templates[0]
    assert updated.context["cookiecutter"]["project_name"] == "new-project"


@pytest.mark.e2e
def test_reparametrize_multi_template_updates_all(tmp_path: Path) -> None:
    """Default reparametrize loops over every link, patching each in its own target dir."""
    repo = _setup_multi_repo(tmp_path, named=False)

    with patch(
        "rebake.reparametrize.prompt_all_variables",
        side_effect=[{"project_name": "new-a"}, {"project_name": "new-b"}],
    ):
        result = runner.invoke(app, ["reparametrize", str(repo)])

    assert result.exit_code == 0, result.output
    assert (repo / "README.md").read_text() == "# new-a\n"
    assert (repo / "batch" / "README.md").read_text() == "# new-b\n"

    templates = RebakeConfig.load(repo).templates
    assert templates[0].context["cookiecutter"]["project_name"] == "new-a"
    assert templates[1].context["cookiecutter"]["project_name"] == "new-b"


@pytest.mark.e2e
def test_reparametrize_multi_template_name_targets_one(tmp_path: Path) -> None:
    """--name reparametrizes only the matching link; the other is left untouched."""
    repo = _setup_multi_repo(tmp_path, named=True)

    with patch(
        "rebake.reparametrize.prompt_all_variables",
        return_value={"project_name": "new-b"},
    ) as mock_prompt:
        result = runner.invoke(app, ["reparametrize", str(repo), "--name", "b"])

    assert result.exit_code == 0, result.output
    mock_prompt.assert_called_once()
    assert (repo / "batch" / "README.md").read_text() == "# new-b\n"
    assert (repo / "README.md").read_text() == "# proj-a\n"

    templates = {e.name: e for e in RebakeConfig.load(repo).templates}
    assert templates["b"].context["cookiecutter"]["project_name"] == "new-b"
    assert templates["a"].context["cookiecutter"]["project_name"] == "proj-a"


@pytest.mark.e2e
def test_reparametrize_multi_template_unknown_name_errors(tmp_path: Path) -> None:
    """An unknown --name errors out end-to-end, leaving every entry intact."""
    repo = _setup_multi_repo(tmp_path, named=True)
    rebake_yaml = repo / "rebake.yaml"
    before = rebake_yaml.read_text()

    result = runner.invoke(app, ["reparametrize", str(repo), "--name", "nope"])

    assert result.exit_code != 0
    assert "No template link named 'nope'" in result.output
    assert rebake_yaml.read_text() == before
