from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
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


def remove_skipped_paths(root: Path, patterns: Sequence[str]) -> None:
    """Delete the paths matching ``skip`` patterns from a rendered template.

    Follows cruft's semantics so a ``.cruft.json`` ``skip`` list keeps its
    meaning: an entry containing ``*`` is a ``Path.glob`` pattern relative to
    ``root`` (so ``*.lock`` is not recursive; use ``**/*.lock``), anything else
    is a literal relative path. A matching directory is removed as a whole.
    """
    root = root.resolve()
    candidates: list[Path] = []
    for pattern in patterns:
        if Path(pattern).is_absolute():
            continue
        if "*" in pattern:
            candidates.extend(root.glob(pattern))
        else:
            candidates.append(root / pattern)

    for candidate in candidates:
        # Normalize lexically so a symlink itself is removed rather than its target,
        # but resolve the parent so neither "../x" nor a path through a symlinked
        # directory can reach outside root.
        path = Path(os.path.normpath(candidate))
        if path == root or not path.parent.resolve().is_relative_to(root):
            continue
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
