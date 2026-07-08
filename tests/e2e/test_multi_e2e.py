from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from cookiecutter.main import cookiecutter
from typer.testing import CliRunner

from rebake.cli import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"

runner = CliRunner()


def _make_template_repo(dest: Path) -> Path:
    shutil.copytree(FIXTURES_DIR / "simple_template", dest)
    subprocess.run(["git", "init", "-b", "main"], cwd=dest, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=dest, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=dest, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=dest, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=dest, capture_output=True, check=True)
    return dest


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True)


def _head_commit(repo: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _render_into(template: Path, target: Path, project_name: str, tmp: Path) -> None:
    """Render a template and place its contents directly under target (wrapper stripped)."""
    out = tmp / f"render_{project_name}"
    out.mkdir()
    rendered = cookiecutter(
        str(template), no_input=True, extra_context={"project_name": project_name}, output_dir=str(out)
    )
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(rendered, target, dirs_exist_ok=True)


@pytest.mark.e2e
def test_multi_update_applies_only_to_changed_template_subdir(tmp_path: Path) -> None:
    template_a = _make_template_repo(tmp_path / "template_a")
    template_b = _make_template_repo(tmp_path / "template_b")
    repo = tmp_path / "repo"
    repo.mkdir()

    # Build a multi-template repo by hand: template_a at root, template_b under batch/.
    _render_into(template_a, repo, "proj-a", tmp_path)
    _render_into(template_b, repo / "batch", "proj-b", tmp_path)
    (repo / "rebake.yaml").write_text(
        yaml.dump(
            {
                "templates": [
                    {
                        "template": str(template_a),
                        "commit": _head_commit(template_a),
                        "context": {"cookiecutter": {"project_name": "proj-a"}},
                    },
                    {
                        "template": str(template_b),
                        "commit": _head_commit(template_b),
                        "directory": "batch",
                        "context": {"cookiecutter": {"project_name": "proj-b"}},
                    },
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        )
    )

    _git(["init"], repo)
    _git(["config", "user.email", "test@test.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    _git(["add", "."], repo)
    _git(["commit", "-m", "init repo"], repo)

    # Advance only template_b.
    (template_b / "{{cookiecutter.project_name}}" / "newfile.txt").write_text("hello\n")
    _git(["add", "."], template_b)
    _git(["commit", "-m", "add newfile"], template_b)

    result = runner.invoke(app, ["update", str(repo)])
    assert result.exit_code == 0, result.output

    # The new file appears only under the batch/ subdir, not at repo root.
    assert (repo / "batch" / "newfile.txt").read_text() == "hello\n"
    assert not (repo / "newfile.txt").exists()

    # Only template_b's commit advanced in the multi-config.
    data = yaml.safe_load((repo / "rebake.yaml").read_text())
    b_entry = next(e for e in data["templates"] if e["template"] == str(template_b))
    assert b_entry["commit"] == _head_commit(template_b)
