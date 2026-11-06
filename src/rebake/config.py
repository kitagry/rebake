from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeGuard, cast

import yaml

REBAKE_FILE = "rebake.yaml"
CRUFT_FILE = ".cruft.json"

# A template link's `name` is user-facing via the CLI (`update --checkout <name>@<ref>`,
# `reparametrize --name <name>`). Restricting it to a slug keeps the config format in
# sync with the CLI grammar: it forbids the empty string and any `@`, so a name can
# never become unreachable through the `<name>@<ref>` parser. Matched with
# `fullmatch` (no anchors) so a trailing newline can't sneak through `$`.
_NAME_RE = re.compile(r"[a-zA-Z0-9_-]+")


def _describe(value: object) -> str:
    # The type name says what went wrong; only null and the empty string need their value shown.
    if value is None:
        return "null"
    return repr(value) if value == "" else type(value).__name__


def _is_str_list(value: object) -> TypeGuard[list[str]]:
    return isinstance(value, list) and all(isinstance(item, str) for item in cast(list[object], value))


def _check_name(name: str) -> None:
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid template link name {name!r}: names must match [a-zA-Z0-9_-]+.")


def _not_a_string(key: str, value: object, *, allow_empty: bool) -> ValueError:
    kind = "a string" if allow_empty else "a non-empty string"
    message = f"'{key}' must be {kind}, got {_describe(value)}."
    # An all-digit short SHA (`commit: 1234567`) or a ref like `checkout: 1.0`
    # loads as a number unless quoted, so say how to fix it.
    if isinstance(value, (bool, int, float)):
        message += " YAML read it as a number or boolean; quote it to keep it a string."
    return ValueError(message)


def _required_str(data: Mapping[str, object], key: str) -> str:
    if key not in data:
        raise ValueError(f"missing required field '{key}'.")
    value = data[key]
    if not isinstance(value, str) or not value:
        raise _not_a_string(key, value, allow_empty=False)
    return value


# An explicit null is read as "absent" for every optional field: cruft writes
# `"checkout": null`, and a bare `skip:` in YAML loads as None.
def _optional_str(data: Mapping[str, object], key: str, *, allow_empty: bool = False) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not (value or allow_empty):
        raise _not_a_string(key, value, allow_empty=allow_empty)
    return value


def _context(data: Mapping[str, object]) -> dict[str, Any]:
    value = data.get("context")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"'context' must be a mapping, got {_describe(value)}.")
    context = cast(dict[str, Any], value)
    # update and reparametrize merge `cookiecutter` as a mapping; the variables
    # inside it are arbitrary template values and are not validated.
    cookiecutter = context.get("cookiecutter")
    if cookiecutter is not None and not isinstance(cookiecutter, dict):
        raise ValueError(f"'context.cookiecutter' must be a mapping, got {_describe(cookiecutter)}.")
    return context


def _name(data: Mapping[str, object]) -> str | None:
    # The empty string is left to the slug check, which explains the allowed characters.
    name = _optional_str(data, "name", allow_empty=True)
    if name is not None:
        _check_name(name)
    return name


def _skip(data: Mapping[str, object]) -> list[str]:
    value = data.get("skip")
    if value is None:
        return []
    if not _is_str_list(value):
        raise ValueError(f"'skip' must be a list of strings, got {_describe(value)}.")
    return value


def _hooks(data: Mapping[str, object]) -> dict[str, list[str]]:
    expected = "'hooks' must be a mapping of hook name to a list of commands"
    value = data.get("hooks")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{expected}, got {_describe(value)}.")
    hooks: dict[str, list[str]] = {}
    for event, commands in cast(dict[object, object], value).items():
        if not isinstance(event, str):
            raise ValueError(f"{expected}, got hook name {event!r}.")
        if commands is None:
            hooks[event] = []
        elif _is_str_list(commands):
            hooks[event] = commands
        else:
            raise ValueError(f"{expected}, got {_describe(commands)} for {event!r}.")
    return hooks


@dataclass
class TemplateEntry:
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
    skip: list[str] = field(default_factory=list[str])
    hooks: dict[str, list[str]] = field(default_factory=dict[str, list[str]])

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "TemplateEntry":
        """Build an entry from one config mapping, raising ``ValueError`` naming the bad field."""
        return cls(
            template=_required_str(data, "template"),
            commit=_required_str(data, "commit"),
            context=_context(data),
            checkout=_optional_str(data, "checkout"),
            name=_name(data),
            # Only rebake's own `target_directory` is honoured. cruft's
            # `directory` (template-side meaning) is ignored on purpose.
            target_directory=_optional_str(data, "target_directory", allow_empty=True) or ".",
            skip=_skip(data),
            hooks=_hooks(data),
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

    templates: list[TemplateEntry]

    def __post_init__(self) -> None:
        # Validate names here so the invariant holds for every RebakeConfig, however
        # it was built: names are slugs and unique. `find_by_name` relies on the
        # uniqueness invariant to return a single entry.
        seen: set[str] = set()
        for entry in self.templates:
            if entry.name is None:
                continue
            _check_name(entry.name)
            if entry.name in seen:
                raise ValueError(f"Duplicate template link name {entry.name!r}: names must be unique.")
            seen.add(entry.name)

    def find_by_name(self, name: str) -> TemplateEntry:
        """Return the single link whose ``name`` matches, or raise ``RuntimeError``.

        Names are unique (enforced in ``__post_init__``), so at most one entry can
        match. Raising here centralizes the lookup and the "not found" message shared
        by ``update`` and ``reparametrize``.
        """
        for entry in self.templates:
            if entry.name == name:
                return entry
        named = [e.name for e in self.templates if e.name]
        if not named:
            raise RuntimeError("No named links in this repo. Add `name:` to the entries you want to target by name.")
        raise RuntimeError(f"No template link named '{name}'. Named links: {', '.join(sorted(named))}.")

    def select(self, names: Sequence[str] | None) -> list[TemplateEntry]:
        """Return the links to operate on, scoped by ``names``.

        Without ``names`` every link is returned. With ``names`` only the links
        whose ``name`` matches are returned, always in config order (independent of
        the order the names were given) and de-duplicated. Every requested name is
        validated via ``find_by_name``, so an unknown name raises ``RuntimeError``
        rather than silently selecting nothing.
        """
        if not names:
            return list(self.templates)
        wanted = {self.find_by_name(name).name for name in names}
        return [entry for entry in self.templates if entry.name in wanted]

    @classmethod
    def load(cls, project_dir: Path = Path(".")) -> "RebakeConfig":
        rebake_file = project_dir / REBAKE_FILE
        cruft_file = project_dir / CRUFT_FILE

        if rebake_file.exists():
            source = rebake_file
            data = yaml.safe_load(rebake_file.read_text())
        elif cruft_file.exists():
            source = cruft_file
            data = json.loads(cruft_file.read_text())
        else:
            raise FileNotFoundError(f"Neither {REBAKE_FILE} nor {CRUFT_FILE} found in {project_dir}")

        try:
            return cls._from_data(data)
        except ValueError as e:
            raise ValueError(f"Invalid config in {source}: {e}") from e

    @classmethod
    def _from_data(cls, data: object) -> "RebakeConfig":
        unrecognized = "Unrecognized config schema: expected a 'templates' list or a top-level 'template' field"
        if not isinstance(data, dict):
            raise ValueError(f"{unrecognized}, got {_describe(data)}.")
        mapping = cast(dict[str, object], data)

        # Multi-template form: {"templates": [...]}
        if "templates" in mapping:
            entries = mapping["templates"]
            if not isinstance(entries, list):
                raise ValueError(f"'templates' must be a list of template links, got {_describe(entries)}.")
            if not entries:
                raise ValueError("'templates' is empty; at least one template link is required.")
            templates: list[TemplateEntry] = []
            for i, entry in enumerate(cast(list[object], entries)):
                if not isinstance(entry, dict):
                    raise ValueError(f"templates[{i}] must be a mapping, got {_describe(entry)}.")
                try:
                    templates.append(TemplateEntry.from_dict(cast(dict[str, object], entry)))
                except ValueError as e:
                    raise ValueError(f"templates[{i}]: {e}") from e
            return cls(templates=templates)

        # Legacy single-template form (rebake.yaml or .cruft.json): {"template": ...}
        if "template" in mapping:
            return cls(templates=[TemplateEntry.from_dict(mapping)])

        raise ValueError(f"{unrecognized}.")

    def save(self, project_dir: Path = Path(".")) -> None:
        if not self.templates:
            raise ValueError("Cannot save a RebakeConfig with no template links.")

        # Always write the `templates:` list form, even for a single template.
        # The read side still accepts the legacy top-level shape and .cruft.json,
        # so this stays one-way backward compatible while keeping one write path.
        out = {"templates": [entry.to_dict() for entry in self.templates]}
        (project_dir / REBAKE_FILE).write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False))

        cruft_file = project_dir / CRUFT_FILE
        if cruft_file.exists():
            cruft_file.unlink()
