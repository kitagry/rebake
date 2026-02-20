import json
import pytest
from pathlib import Path
from unittest.mock import patch

from rebake.utils.variables import detect_new_variables, prompt_new_variables


def make_template_dir(tmp_path: Path, cookiecutter_json: dict) -> Path:
    template_dir = tmp_path / "template"
    template_dir.mkdir()
    (template_dir / "cookiecutter.json").write_text(json.dumps(cookiecutter_json))
    return template_dir


def test_detect_no_new_variables(tmp_path):
    template_dir = make_template_dir(
        tmp_path, {"project_name": "default", "author": "Me"}
    )
    old_context = {"project_name": "my-project", "author": "Jane"}

    result = detect_new_variables(template_dir, old_context)

    assert result == {}


def test_detect_new_variable(tmp_path):
    template_dir = make_template_dir(
        tmp_path, {"project_name": "default", "author": "Me", "license": "MIT"}
    )
    old_context = {"project_name": "my-project", "author": "Jane"}

    result = detect_new_variables(template_dir, old_context)

    assert result == {"license": "MIT"}


def test_detect_ignores_private_variables(tmp_path):
    # _で始まる変数はcookiecutterの内部変数なので無視する
    template_dir = make_template_dir(
        tmp_path, {"project_name": "default", "_extensions": [], "new_var": "value"}
    )
    old_context = {"project_name": "my-project"}

    result = detect_new_variables(template_dir, old_context)

    assert result == {"new_var": "value"}
    assert "_extensions" not in result


def test_prompt_new_variables_returns_user_input(tmp_path):
    template_dir = make_template_dir(
        tmp_path, {"project_name": "default", "license": "MIT"}
    )
    new_vars = {"license": "MIT"}

    with patch("rebake.utils.variables.cookiecutter_prompt", return_value={"license": "Apache-2.0"}):
        result = prompt_new_variables(new_vars)

    assert result == {"license": "Apache-2.0"}
