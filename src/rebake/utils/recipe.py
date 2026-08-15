from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict, cast

import yaml

RECIPE_FILE = "rebake-recipe.yaml"

# Hook events fired around `rebake update`. Defined via the functional TypedDict
# form because the keys contain a hyphen, which is not a valid Python identifier
# in the class-based form. `total=False` lets a recipe declare only one of the
# two events without satisfying the other.
HookSpec = TypedDict(
    "HookSpec",
    {
        "pre-update": list[str],
        "post-update": list[str],
    },
    total=False,
)


@dataclass
class Recipe:
    """Template-side rebake recipe.

    Holds default hooks the template author wants applied to every generated
    project. Loaded from rebake-recipe.yaml at the template root and merged
    into the generated project's rebake.yaml.hooks via a 3-way merge on update.
    """

    hooks: HookSpec = field(default_factory=lambda: cast(HookSpec, {}))


@dataclass
class HookMergeConflict:
    """One unresolved hunk in a 3-way merge of a hook event."""

    event: str  # e.g. "pre-update"
    hunk_count: int  # number of conflict hunks for this event


@dataclass
class HookMergeResult:
    """Outcome of a 3-way merge of hooks.

    `hooks` always carries the merged result. When `conflicts` is empty the
    merge was clean and the lists contain only real commands. When conflicts
    occurred, the affected event's list embeds git-style markers
    (`<<<<<<< ours`, `=======`, `>>>>>>> theirs`) as plain entries so the
    caller can write them straight back into rebake.yaml for the user to
    resolve by hand.
    """

    hooks: HookSpec
    conflicts: list[HookMergeConflict] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


def load_recipe(template_dir: Path) -> Recipe:
    """Load rebake-recipe.yaml from a cloned template directory.

    Returns an empty Recipe when the file is absent (template authors that
    do not need recipe hooks are unaffected).

    Raises ValueError when the file exists but has an unexpected shape, so
    template authoring mistakes fail loudly instead of silently dropping hooks.
    """
    recipe_path = template_dir / RECIPE_FILE
    if not recipe_path.exists():
        return Recipe()

    raw = yaml.safe_load(recipe_path.read_text())
    if raw is None:
        return Recipe()
    if not isinstance(raw, dict):
        raise ValueError(f"{RECIPE_FILE}: top-level must be a mapping, got {type(raw).__name__}")

    hooks_raw = raw.get("hooks", {})
    if not isinstance(hooks_raw, dict):
        raise ValueError(f"{RECIPE_FILE}: 'hooks' must be a mapping, got {type(hooks_raw).__name__}")

    valid_events = tuple(HookSpec.__annotations__.keys())
    hooks: dict[str, list[str]] = {}
    for event, commands in hooks_raw.items():
        if event not in valid_events:
            raise ValueError(f"{RECIPE_FILE}: unsupported hook event {event!r} (expected one of {valid_events})")
        if not isinstance(commands, list) or not all(isinstance(c, str) for c in commands):
            raise ValueError(f"{RECIPE_FILE}: hooks.{event} must be a list of strings")
        hooks[event] = list(commands)

    return Recipe(hooks=cast(HookSpec, hooks))


def merge_hooks(*, base: HookSpec, theirs: HookSpec, ours: HookSpec) -> HookMergeResult:
    """3-way merge of hook lists per event using git merge-file.

    `base` is the recipe hooks at the previously-applied template commit.
    `theirs` is the recipe hooks at the new template commit.
    `ours` is the current rebake.yaml.hooks (what the user has now).

    Returns a HookMergeResult. On a clean merge `conflicts` is empty and
    `hooks` contains only commands. When merging an event hits an unresolved
    hunk, that event's list in `hooks` keeps the git-style conflict markers
    as plain entries (so they survive a YAML round trip and the caller can
    write them straight to rebake.yaml).
    """
    merged: dict[str, list[str]] = {}
    conflicts: list[HookMergeConflict] = []
    events = set(base.keys()) | set(theirs.keys()) | set(ours.keys())
    # Use cast to read each side as a plain dict, since TypedDict.get with a
    # default trips type inference on `total=False` keys.
    base_d = cast("dict[str, list[str]]", base)
    theirs_d = cast("dict[str, list[str]]", theirs)
    ours_d = cast("dict[str, list[str]]", ours)
    for event in events:
        merged_list, hunk_count = _merge_line_lists(
            base=base_d.get(event, []),
            theirs=theirs_d.get(event, []),
            ours=ours_d.get(event, []),
            event=event,
        )
        if hunk_count > 0:
            conflicts.append(HookMergeConflict(event=event, hunk_count=hunk_count))
        # Drop events that ended up empty so the caller does not emit "post-update: []".
        if merged_list:
            merged[event] = merged_list
    return HookMergeResult(hooks=cast(HookSpec, merged), conflicts=conflicts)


def _merge_line_lists(*, base: list[str], theirs: list[str], ours: list[str], event: str) -> tuple[list[str], int]:
    """Run git merge-file on three line lists.

    Returns (merged_list, hunk_count). hunk_count is 0 for a clean merge;
    otherwise the merged list contains git-style conflict marker entries
    (`<<<<<<< ours`, `=======`, `>>>>>>> theirs`).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        base_path = tmp / "base"
        theirs_path = tmp / "theirs"
        ours_path = tmp / "ours"
        # Trailing newline so git merge-file treats the last line as complete.
        base_path.write_text(_to_text(base))
        theirs_path.write_text(_to_text(theirs))
        ours_path.write_text(_to_text(ours))

        # git merge-file rewrites ours_path in place and returns the conflict
        # count (0 = clean, >0 = number of conflict hunks, <0 = error).
        result = subprocess.run(
            [
                "git",
                "merge-file",
                "-L",
                "ours",
                "-L",
                "base",
                "-L",
                "theirs",
                "--quiet",
                str(ours_path),
                str(base_path),
                str(theirs_path),
            ],
            capture_output=True,
        )
        if result.returncode < 0:
            raise RuntimeError(
                f"git merge-file failed for hooks.{event} (exit {result.returncode}): "
                f"{result.stderr.decode(errors='replace')}"
            )
        return _from_text(ours_path.read_text()), result.returncode


def _to_text(lines: list[str]) -> str:
    """Serialize a list of commands as one command per line."""
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _from_text(text: str) -> list[str]:
    """Parse a merged file back into a list of commands (one per non-empty line)."""
    return [line for line in text.split("\n") if line]
