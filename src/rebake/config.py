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
    """A single template link.

    A repository may register more than one of these (see ``RebakeConfig``);
    ``directory`` is the sub-path within the repository that this template's
    patches are applied to (``"."`` for the repository root).
    """

    template: str
    commit: str
    context: dict[str, Any]
    checkout: str | None = None
    directory: str = "."
    skip: list[str] = field(default_factory=list)
    hooks: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CruftConfig":
        return cls(
            template=data["template"],
            commit=data["commit"],
            context=data.get("context", {}),
            checkout=data.get("checkout"),
            # A legacy cruft .cruft.json carries `directory` (its own, unrelated
            # meaning) often as null; treat null/absent/empty as the repo root.
            directory=data.get("directory") or ".",
            skip=data.get("skip", []),
            hooks=data.get("hooks", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "template": self.template,
            "commit": self.commit,
            "context": self.context,
        }
        if self.checkout is not None:
            data["checkout"] = self.checkout
        if self.directory != ".":
            data["directory"] = self.directory
        if self.skip:
            data["skip"] = self.skip
        if self.hooks:
            data["hooks"] = self.hooks
        return data

    @classmethod
    def load(cls, project_dir: Path = Path(".")) -> "CruftConfig":
        """Load the first template link (backward-compatible single-template API)."""
        return RebakeConfig.load(project_dir).templates[0]

    def save(self, project_dir: Path = Path(".")) -> None:
        """Write this single template link in the legacy top-level form."""
        rebake_file = project_dir / REBAKE_FILE
        rebake_file.write_text(yaml.dump(self.to_dict(), allow_unicode=True, sort_keys=False))

        cruft_file = project_dir / CRUFT_FILE
        if cruft_file.exists():
            cruft_file.unlink()


@dataclass
class RebakeConfig:
    """All template links registered in a repository's ``rebake.yaml``."""

    templates: list[CruftConfig]

    @classmethod
    def load(cls, project_dir: Path = Path(".")) -> "RebakeConfig":
        rebake_file = project_dir / REBAKE_FILE
        cruft_file = project_dir / CRUFT_FILE

        if rebake_file.exists():
            data = yaml.safe_load(rebake_file.read_text())
        elif cruft_file.exists():
            data = json.loads(cruft_file.read_text())
        else:
            raise FileNotFoundError(f"Neither {REBAKE_FILE} nor {CRUFT_FILE} found in {project_dir}")

        # Multi-template form: {"templates": [...]}
        if isinstance(data, dict) and "templates" in data:
            return cls(templates=[CruftConfig.from_dict(entry) for entry in data["templates"]])

        # Legacy single-template form (rebake.yaml or .cruft.json): {"template": ...}
        if isinstance(data, dict) and "template" in data:
            return cls(templates=[CruftConfig.from_dict(data)])

        raise ValueError(f"Unrecognized config schema in {project_dir}")

    def save(self, project_dir: Path = Path(".")) -> None:
        if not self.templates:
            raise ValueError("Cannot save a RebakeConfig with no template links.")

        # Keep the legacy top-level shape for single-template repos so existing
        # repositories and tooling see no schema change; only multi-template
        # repos get the `templates:` list form.
        if len(self.templates) == 1:
            self.templates[0].save(project_dir)
            return

        out = {"templates": [entry.to_dict() for entry in self.templates]}
        (project_dir / REBAKE_FILE).write_text(yaml.dump(out, allow_unicode=True, sort_keys=False))

        cruft_file = project_dir / CRUFT_FILE
        if cruft_file.exists():
            cruft_file.unlink()
