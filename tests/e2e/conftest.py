from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from cookiecutter.main import cookiecutter

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], capture_output=True, text=True, check=True, cwd=cwd)


def _head_commit(repo: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo,
    )
    return result.stdout.strip()


@pytest.fixture
def template_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "template"
    shutil.copytree(FIXTURES_DIR / "simple_template", repo)
    _git(["init"], repo)
    _git(["config", "user.email", "test@test.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    _git(["add", "."], repo)
    _git(["commit", "-m", "init"], repo)
    return repo


@pytest.fixture
def project_dir(tmp_path: Path, template_repo: Path) -> Path:
    commit = _head_commit(template_repo)

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    rendered = cookiecutter(
        str(template_repo),
        no_input=True,
        extra_context={"project_name": "my-project"},
        output_dir=str(output_dir),
    )
    project = Path(rendered)

    (project / ".cruft.json").write_text(
        json.dumps(
            {
                "template": str(template_repo),
                "commit": commit,
                "context": {"cookiecutter": {"project_name": "my-project"}},
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    _git(["init"], project)
    _git(["config", "user.email", "test@test.com"], project)
    _git(["config", "user.name", "Test"], project)
    _git(["add", "."], project)
    _git(["commit", "-m", "init project"], project)

    return project
