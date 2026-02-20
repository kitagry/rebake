from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cookiecutter.prompt import prompt_for_config


def detect_new_variables(template_dir: Path, old_context: dict[str, Any]) -> dict[str, Any]:
    """Return variables present in the template but absent from the saved context.

    Private variables (prefixed with '_') are excluded because they are
    cookiecutter internals and should not be prompted.
    """
    cookiecutter_json = template_dir / "cookiecutter.json"
    template_vars: dict[str, Any] = json.loads(cookiecutter_json.read_text())
    return {k: v for k, v in template_vars.items() if k not in old_context and not k.startswith("_")}


def cookiecutter_prompt(new_vars: dict[str, Any]) -> dict[str, Any]:
    """Thin wrapper around cookiecutter's interactive prompt.

    Isolated here so tests can patch it without touching cookiecutter internals.
    """
    return prompt_for_config({"cookiecutter": new_vars}, no_input=False)


def prompt_new_variables(new_vars: dict[str, Any]) -> dict[str, Any]:
    """Interactively ask the user for values of newly added template variables."""
    return cookiecutter_prompt(new_vars)
