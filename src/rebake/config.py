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
    ``target_directory`` is the sub-path within the repository that this
    template's patches are applied to (``"."`` for the repository root).

    ``name`` is an optional label used to target this link from the CLI, e.g.
    ``rebake update --checkout <name>@<ref>`` on a multi-template repository.

    ``target_directory`` is deliberately *not* named ``directory``: cruft's
    ``.cruft.json`` already uses ``directory`` for the opposite thing (a
    sub-directory **inside the template repo**, i.e. cookiecutter's
    ``--directory``). Reusing that name would silently misread a cruft-authored
    config and apply patches to the wrong place, so ``directory`` is left
    untouched (and reserved for a future template-side feature).
    """

    template: str
    commit: str
    context: dict[str, Any]
    checkout: str | None = None
    name: str | None = None
    target_directory: str = "."
    skip: list[str] = field(default_factory=list)
    hooks: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CruftConfig":
        return cls(
            template=data["template"],
            commit=data["commit"],
            context=data.get("context", {}),
            checkout=data.get("checkout"),
            name=data.get("name"),
            # Only rebake's own `target_directory` is honoured. cruft's
            # `directory` (template-side meaning) is ignored on purpose.
            target_directory=data.get("target_directory") or ".",
            skip=data.get("skip", []),
            hooks=data.get("hooks", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "template": self.template,
            "commit": self.commit,
        }
        if self.name is not None:
            data["name"] = self.name
        data["context"] = self.context
        if self.checkout is not None:
            data["checkout"] = self.checkout
        if self.target_directory != ".":
            data["target_directory"] = self.target_directory
        if self.skip:
            data["skip"] = self.skip
        if self.hooks:
            data["hooks"] = self.hooks
        return data


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
            entries = data["templates"]
            if not entries:
                raise ValueError(f"'templates' is empty in {project_dir}; at least one template link is required.")
            return cls(templates=[CruftConfig.from_dict(entry) for entry in entries])

        # Legacy single-template form (rebake.yaml or .cruft.json): {"template": ...}
        if isinstance(data, dict) and "template" in data:
            return cls(templates=[CruftConfig.from_dict(data)])

        raise ValueError(f"Unrecognized config schema in {project_dir}")

    def save(self, project_dir: Path = Path(".")) -> None:
        if not self.templates:
            raise ValueError("Cannot save a RebakeConfig with no template links.")

        # Always write the `templates:` list form, even for a single template.
        # The read side still accepts the legacy top-level shape and .cruft.json,
        # so this stays one-way backward compatible while keeping one write path.
        out = {"templates": [entry.to_dict() for entry in self.templates]}
        (project_dir / REBAKE_FILE).write_text(yaml.dump(out, allow_unicode=True, sort_keys=False))

        cruft_file = project_dir / CRUFT_FILE
        if cruft_file.exists():
            cruft_file.unlink()
