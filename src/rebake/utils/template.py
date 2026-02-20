from __future__ import annotations

from pathlib import Path
from typing import Any

from cookiecutter.main import cookiecutter


def render_template(template_dir: Path, context: dict[str, Any], output_dir: Path) -> Path:
    """Render a cookiecutter template into output_dir without user prompts.

    Returns the path to the rendered project directory.
    """
    result = cookiecutter(
        str(template_dir),
        no_input=True,
        extra_context=context,
        output_dir=str(output_dir),
    )
    return Path(result)
