from __future__ import annotations

import os
import subprocess
from pathlib import Path


def run_hooks(event: str, project_dir: Path, commands: list[str], env: dict[str, str] | None = None) -> None:
    merged_env = {**os.environ, **(env or {})}
    for cmd in commands:
        result = subprocess.run(cmd, shell=True, cwd=project_dir, env=merged_env)
        if result.returncode != 0:
            raise RuntimeError(f"Hook '{event}' failed (command: {cmd!r}, exit code: {result.returncode})")
