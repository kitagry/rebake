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


def _commit_rebake_yaml(project_dir: Path, hooks: dict) -> None:
    import yaml

    rebake_cfg = yaml.safe_load((project_dir / "rebake.yaml").read_text())
    rebake_cfg["hooks"] = hooks
    (project_dir / "rebake.yaml").write_text(yaml.dump(rebake_cfg, allow_unicode=True, sort_keys=False))
    subprocess.run(["git", "add", "rebake.yaml"], cwd=project_dir, check=True)
    subprocess.run(["git", "commit", "-m", "add hooks"], cwd=project_dir, check=True)


@pytest.mark.e2e
def test_update_runs_pre_update_hook(project_dir: Path, template_repo: Path) -> None:
    sentinel = project_dir / "pre_hook_ran"
    _commit_rebake_yaml(project_dir, {"pre-update": [f"touch {sentinel}"]})

    result = runner.invoke(app, ["update", str(project_dir)])
    assert result.exit_code == 0
    assert sentinel.exists()


@pytest.mark.e2e
def test_update_runs_post_update_hook(project_dir: Path, template_repo: Path) -> None:
    sentinel = project_dir / "post_hook_ran"
    _commit_rebake_yaml(project_dir, {"post-update": [f"touch {sentinel}"]})

    result = runner.invoke(app, ["update", str(project_dir)])
    assert result.exit_code == 0
    assert sentinel.exists()


@pytest.mark.e2e
def test_update_pre_hook_failure_aborts_update(project_dir: Path, template_repo: Path) -> None:
    new_file = template_repo / "{{cookiecutter.project_name}}" / "newfile.txt"
    new_file.write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=template_repo, check=True)
    subprocess.run(["git", "commit", "-m", "add newfile.txt"], cwd=template_repo, check=True)

    _commit_rebake_yaml(project_dir, {"pre-update": ["exit 1"]})

    result = runner.invoke(app, ["update", str(project_dir)])
    assert result.exit_code != 0
    assert not (project_dir / "newfile.txt").exists()


@pytest.mark.e2e
def test_update_hook_receives_env_vars(project_dir: Path, template_repo: Path) -> None:
    out = project_dir / "env_out.txt"
    _commit_rebake_yaml(project_dir, {"post-update": [f"echo $REBAKE_TEMPLATE > {out}"]})

    result = runner.invoke(app, ["update", str(project_dir)])
    assert result.exit_code == 0
    assert str(template_repo) in out.read_text()


@pytest.mark.e2e
def test_update_with_checkout_stops_at_midway_commit(project_dir: Path, template_repo: Path) -> None:
    # commit1: add file1.txt, tag as v1 (midway)
    (template_repo / "{{cookiecutter.project_name}}" / "file1.txt").write_text("file1\n")
    subprocess.run(["git", "add", "."], cwd=template_repo, check=True)
    subprocess.run(["git", "commit", "-m", "add file1.txt"], cwd=template_repo, check=True)
    subprocess.run(["git", "tag", "v1"], cwd=template_repo, check=True)

    # commit2: add file2.txt (HEAD)
    (template_repo / "{{cookiecutter.project_name}}" / "file2.txt").write_text("file2\n")
    subprocess.run(["git", "add", "."], cwd=template_repo, check=True)
    subprocess.run(["git", "commit", "-m", "add file2.txt"], cwd=template_repo, check=True)

    result = runner.invoke(app, ["update", "--checkout", "v1", str(project_dir)])
    assert result.exit_code == 0
    assert (project_dir / "file1.txt").read_text() == "file1\n"
    assert not (project_dir / "file2.txt").exists()

    import yaml

    config = yaml.safe_load((project_dir / "rebake.yaml").read_text())
    assert config["checkout"] == "v1"
