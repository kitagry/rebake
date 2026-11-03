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
    return _template_at(tmp_path / "template")


def _template_at(dest: Path) -> Path:
    shutil.copytree(FIXTURES_DIR / "simple_template", dest)
    subprocess.run(["git", "init", "-b", "main"], cwd=dest, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=dest, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=dest, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=dest, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=dest, capture_output=True, check=True)
    return dest


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
    entry = yaml.safe_load(rebake_yaml.read_text())["templates"][0]
    assert entry["template"] == str(template_repo)
    assert "commit" in entry
    assert len(entry["commit"]) == 40  # SHA-1 full hash
    assert entry["context"]["cookiecutter"]["project_name"] == "my-project"


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
    entry = yaml.safe_load((output_dir / "my-project" / "rebake.yaml").read_text())["templates"][0]
    assert entry["checkout"] == "main"


@pytest.mark.e2e
def test_create_multi_renders_first_and_later_templates_in_order(tmp_path: Path) -> None:
    first = _template_at(tmp_path / "t_first")
    template_b = _template_at(tmp_path / "t_b")
    template_c = _template_at(tmp_path / "t_c")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "create",
            str(first),
            "--output-dir",
            str(output_dir),
            f"{template_b}=batch",
            f"{template_c}=api",
        ],
        input="proj-a\nproj-b\nproj-c\n",  # cookiecutter prompts follow argument order
    )

    assert result.exit_code == 0, result.output
    project = output_dir / "proj-a"
    assert (project / "README.md").read_text().strip() == "# proj-a"
    assert (project / "batch" / "README.md").read_text().strip() == "# proj-b"
    assert (project / "api" / "README.md").read_text().strip() == "# proj-c"
    # cookiecutter's project-name wrapper is stripped inside the sub-directories.
    assert not (project / "batch" / "proj-b").exists()

    templates = yaml.safe_load((project / "rebake.yaml").read_text())["templates"]
    assert [t["template"] for t in templates] == [str(first), str(template_b), str(template_c)]
    assert "target_directory" not in templates[0]
    assert templates[1]["target_directory"] == "batch"
    assert templates[2]["target_directory"] == "api"


@pytest.mark.e2e
def test_create_multi_root_overlay_later_copy_wins_during_create(tmp_path: Path) -> None:
    first = _template_at(tmp_path / "t_first")
    template_b = _template_at(tmp_path / "t_b")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # A bare later spec (no =TARGET) renders the second template at the root too.
    result = runner.invoke(
        app,
        ["create", str(first), "--output-dir", str(output_dir), str(template_b)],
        input="proj-a\nproj-b\n",
    )

    assert result.exit_code == 0, result.output
    project = output_dir / "proj-a"  # the first template establishes the project directory name
    # Both templates render at the root; on collision the later copy wins during create.
    assert (project / "README.md").read_text().strip() == "# proj-b"

    templates = yaml.safe_load((project / "rebake.yaml").read_text())["templates"]
    assert [t["template"] for t in templates] == [str(first), str(template_b)]
    # Both target the repo root, so "." is omitted from every saved entry.
    assert all("target_directory" not in t for t in templates)


@pytest.mark.e2e
def test_create_rejects_invalid_later_template_spec(tmp_path: Path) -> None:
    first = _template_at(tmp_path / "t_first")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # A later spec with an empty target ("=") is rejected before rendering.
    result = runner.invoke(
        app,
        ["create", str(first), "--output-dir", str(output_dir), f"{first}="],
    )

    assert result.exit_code == 1
    # The parse guard fires before rendering, so nothing is written.
    assert list(output_dir.iterdir()) == []
