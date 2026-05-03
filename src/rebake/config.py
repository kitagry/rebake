from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REBAKE_FILE = "rebake.yaml"
CRUFT_FILE = ".cruft.json"


@dataclass
class CruftConfig:
    template: str
    commit: str
    context: dict[str, Any]
    checkout: str | None = None
    skip: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, project_dir: Path = Path(".")) -> "CruftConfig":
        rebake_file = project_dir / REBAKE_FILE
        cruft_file = project_dir / CRUFT_FILE

        if rebake_file.exists():
            data = yaml.safe_load(rebake_file.read_text())
        elif cruft_file.exists():
            data = json.loads(cruft_file.read_text())
        else:
            raise FileNotFoundError(f"Neither {REBAKE_FILE} nor {CRUFT_FILE} found in {project_dir}")

        return cls(
            template=data["template"],
            commit=data["commit"],
            context=data.get("context", {}),
            checkout=data.get("checkout"),
            skip=data.get("skip", []),
        )

    def save(self, project_dir: Path = Path(".")) -> None:
        data: dict[str, Any] = {
            "template": self.template,
            "commit": self.commit,
            "context": self.context,
        }
        if self.checkout is not None:
            data["checkout"] = self.checkout
        if self.skip:
            data["skip"] = self.skip

        rebake_file = project_dir / REBAKE_FILE
        rebake_file.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False))

        cruft_file = project_dir / CRUFT_FILE
        if cruft_file.exists():
            cruft_file.unlink()
