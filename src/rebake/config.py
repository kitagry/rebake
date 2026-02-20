from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
        cruft_file = project_dir / CRUFT_FILE
        if not cruft_file.exists():
            raise FileNotFoundError(f"{CRUFT_FILE} not found in {project_dir}")
        data = json.loads(cruft_file.read_text())
        return cls(
            template=data["template"],
            commit=data["commit"],
            context=data.get("context", {}),
            checkout=data.get("checkout"),
            skip=data.get("skip", []),
        )

    def save(self, project_dir: Path = Path(".")) -> None:
        cruft_file = project_dir / CRUFT_FILE
        data: dict[str, Any] = {
            "template": self.template,
            "commit": self.commit,
            "context": self.context,
        }
        if self.checkout is not None:
            data["checkout"] = self.checkout
        if self.skip:
            data["skip"] = self.skip
        cruft_file.write_text(json.dumps(data, indent=2) + "\n")
