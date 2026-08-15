from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from rebake.utils.recipe import (
    RECIPE_FILE,
    HookMergeConflict,
    HookMergeResult,
    Recipe,
    load_recipe,
    merge_hooks,
)

# ---------------------------------------------------------------------------
# load_recipe
# ---------------------------------------------------------------------------


def test_load_recipe_missing_file_returns_empty(tmp_path: Path) -> None:
    recipe = load_recipe(tmp_path)

    assert recipe == Recipe()


def test_load_recipe_empty_yaml_returns_empty(tmp_path: Path) -> None:
    (tmp_path / RECIPE_FILE).write_text("")

    recipe = load_recipe(tmp_path)

    assert recipe == Recipe()


def test_load_recipe_parses_hooks(tmp_path: Path) -> None:
    (tmp_path / RECIPE_FILE).write_text(
        yaml.dump(
            {
                "hooks": {
                    "pre-update": ["echo pre"],
                    "post-update": ["echo post-1", "echo post-2"],
                }
            }
        )
    )

    recipe = load_recipe(tmp_path)

    assert recipe == Recipe(
        hooks={
            "pre-update": ["echo pre"],
            "post-update": ["echo post-1", "echo post-2"],
        }
    )


def test_load_recipe_without_hooks_key_returns_empty_hooks(tmp_path: Path) -> None:
    (tmp_path / RECIPE_FILE).write_text(yaml.dump({"other": "value"}))

    recipe = load_recipe(tmp_path)

    assert recipe == Recipe()


def test_load_recipe_rejects_non_mapping_top_level(tmp_path: Path) -> None:
    (tmp_path / RECIPE_FILE).write_text(yaml.dump(["just", "a", "list"]))

    with pytest.raises(ValueError, match="top-level must be a mapping"):
        load_recipe(tmp_path)


def test_load_recipe_rejects_non_mapping_hooks(tmp_path: Path) -> None:
    (tmp_path / RECIPE_FILE).write_text(yaml.dump({"hooks": ["pre-update"]}))

    with pytest.raises(ValueError, match="'hooks' must be a mapping"):
        load_recipe(tmp_path)


def test_load_recipe_rejects_unknown_event(tmp_path: Path) -> None:
    (tmp_path / RECIPE_FILE).write_text(yaml.dump({"hooks": {"pre-create": ["echo"]}}))

    with pytest.raises(ValueError, match="unsupported hook event"):
        load_recipe(tmp_path)


def test_load_recipe_rejects_non_string_command(tmp_path: Path) -> None:
    (tmp_path / RECIPE_FILE).write_text(yaml.dump({"hooks": {"pre-update": [{"cmd": "echo hi"}]}}))

    with pytest.raises(ValueError, match="must be a list of strings"):
        load_recipe(tmp_path)


def test_load_recipe_rejects_non_list_commands(tmp_path: Path) -> None:
    (tmp_path / RECIPE_FILE).write_text(yaml.dump({"hooks": {"pre-update": "echo single"}}))

    with pytest.raises(ValueError, match="must be a list of strings"):
        load_recipe(tmp_path)


# ---------------------------------------------------------------------------
# merge_hooks (3-way merge)
# ---------------------------------------------------------------------------


def test_merge_hooks_all_empty_returns_empty_result() -> None:
    assert merge_hooks(base={}, theirs={}, ours={}) == HookMergeResult(hooks={})


def test_merge_hooks_no_changes_returns_ours_verbatim() -> None:
    """If base == theirs == ours, the merge is a no-op."""
    hooks: dict[str, list[str]] = {"post-update": ["echo a", "echo b"]}

    assert merge_hooks(base=hooks, theirs=hooks, ours=hooks) == HookMergeResult(hooks=hooks)


def test_merge_hooks_user_only_addition_keeps_user_entry() -> None:
    """User appended an entry; recipe did not change → keep the user entry."""
    base: dict[str, list[str]] = {"post-update": ["echo a"]}
    theirs: dict[str, list[str]] = {"post-update": ["echo a"]}
    ours: dict[str, list[str]] = {"post-update": ["echo a", "echo user"]}

    assert merge_hooks(base=base, theirs=theirs, ours=ours) == HookMergeResult(hooks=ours)


def test_merge_hooks_recipe_only_addition_picks_up_recipe_entry() -> None:
    """Recipe added an entry; user did not change → adopt the recipe entry."""
    base: dict[str, list[str]] = {"post-update": ["echo a"]}
    theirs: dict[str, list[str]] = {"post-update": ["echo a", "echo new"]}
    ours: dict[str, list[str]] = {"post-update": ["echo a"]}

    assert merge_hooks(base=base, theirs=theirs, ours=ours) == HookMergeResult(
        hooks={"post-update": ["echo a", "echo new"]}
    )


def test_merge_hooks_recipe_appends_user_prepends_merges_cleanly() -> None:
    """Recipe appends, user prepends → non-overlapping hunks merge cleanly."""
    base: dict[str, list[str]] = {"post-update": ["echo a"]}
    theirs: dict[str, list[str]] = {"post-update": ["echo a", "echo recipe-added"]}
    ours: dict[str, list[str]] = {"post-update": ["echo user-added", "echo a"]}

    assert merge_hooks(base=base, theirs=theirs, ours=ours) == HookMergeResult(
        hooks={"post-update": ["echo user-added", "echo a", "echo recipe-added"]}
    )


def test_merge_hooks_recipe_removed_entry_drops_it() -> None:
    """Recipe dropped an entry; user did not touch it → it goes away."""
    base: dict[str, list[str]] = {"post-update": ["echo a", "echo b"]}
    theirs: dict[str, list[str]] = {"post-update": ["echo a"]}
    ours: dict[str, list[str]] = {"post-update": ["echo a", "echo b"]}

    assert merge_hooks(base=base, theirs=theirs, ours=ours) == HookMergeResult(hooks={"post-update": ["echo a"]})


def test_merge_hooks_independent_events_merge_independently() -> None:
    """pre-update changes do not affect post-update merge and vice versa."""
    base: dict[str, list[str]] = {"pre-update": ["echo p"], "post-update": ["echo q"]}
    theirs: dict[str, list[str]] = {"pre-update": ["echo p2"], "post-update": ["echo q"]}
    ours: dict[str, list[str]] = {"pre-update": ["echo p"], "post-update": ["echo q", "echo user"]}

    assert merge_hooks(base=base, theirs=theirs, ours=ours) == HookMergeResult(
        hooks={
            "pre-update": ["echo p2"],
            "post-update": ["echo q", "echo user"],
        }
    )


def test_merge_hooks_conflict_embeds_markers_and_records_conflict() -> None:
    """On conflict, the affected event's list contains git-style markers as
    plain entries, and the result records the conflict; input dicts are not mutated."""
    base: dict[str, list[str]] = {"post-update": ["echo a"]}
    theirs: dict[str, list[str]] = {"post-update": ["echo theirs"]}
    ours: dict[str, list[str]] = {"post-update": ["echo ours"]}
    snapshot = copy.deepcopy((base, theirs, ours))

    result = merge_hooks(base=base, theirs=theirs, ours=ours)

    assert result == HookMergeResult(
        hooks={
            "post-update": [
                "<<<<<<< ours",
                "echo ours",
                "=======",
                "echo theirs",
                ">>>>>>> theirs",
            ],
        },
        conflicts=[HookMergeConflict(event="post-update", hunk_count=1)],
    )
    assert result.has_conflicts is True
    # Inputs are untouched.
    assert (base, theirs, ours) == snapshot


def test_merge_hooks_both_added_at_same_position_conflicts() -> None:
    """Recipe and user both append to the same tail → line-based merge conflicts.

    git merge-file is line-based, so two simultaneous tail-additions land in
    the same hunk and surface as a conflict.
    """
    base: dict[str, list[str]] = {"post-update": ["echo a"]}
    theirs: dict[str, list[str]] = {"post-update": ["echo a", "echo recipe-added"]}
    ours: dict[str, list[str]] = {"post-update": ["echo a", "echo user-added"]}

    result = merge_hooks(base=base, theirs=theirs, ours=ours)

    assert result.has_conflicts is True
    assert result.conflicts == [HookMergeConflict(event="post-update", hunk_count=1)]
    # The affected event has marker entries; the other (absent) events are untouched.
    assert any(line.startswith("<<<<<<<") for line in result.hooks["post-update"])


def test_merge_hooks_conflict_in_one_event_and_clean_merge_in_another() -> None:
    """A conflict in pre-update must not stop post-update from merging cleanly."""
    base: dict[str, list[str]] = {
        "pre-update": ["echo a"],
        "post-update": ["echo p"],
    }
    theirs: dict[str, list[str]] = {
        "pre-update": ["echo theirs"],
        "post-update": ["echo p", "echo recipe-added"],
    }
    ours: dict[str, list[str]] = {
        "pre-update": ["echo ours"],
        "post-update": ["echo p"],
    }

    result = merge_hooks(base=base, theirs=theirs, ours=ours)

    assert result == HookMergeResult(
        hooks={
            "pre-update": [
                "<<<<<<< ours",
                "echo ours",
                "=======",
                "echo theirs",
                ">>>>>>> theirs",
            ],
            "post-update": ["echo p", "echo recipe-added"],
        },
        conflicts=[HookMergeConflict(event="pre-update", hunk_count=1)],
    )


def test_merge_hooks_conflict_in_both_events_records_both() -> None:
    """Independent conflicts in pre-update and post-update both surface."""
    base: dict[str, list[str]] = {"pre-update": ["echo a"], "post-update": ["echo b"]}
    theirs: dict[str, list[str]] = {"pre-update": ["echo theirs-a"], "post-update": ["echo theirs-b"]}
    ours: dict[str, list[str]] = {"pre-update": ["echo ours-a"], "post-update": ["echo ours-b"]}

    result = merge_hooks(base=base, theirs=theirs, ours=ours)

    assert sorted(result.conflicts, key=lambda c: c.event) == [
        HookMergeConflict(event="post-update", hunk_count=1),
        HookMergeConflict(event="pre-update", hunk_count=1),
    ]
    # Each event has its own conflict markers.
    assert result.hooks["pre-update"] == [
        "<<<<<<< ours",
        "echo ours-a",
        "=======",
        "echo theirs-a",
        ">>>>>>> theirs",
    ]
    assert result.hooks["post-update"] == [
        "<<<<<<< ours",
        "echo ours-b",
        "=======",
        "echo theirs-b",
        ">>>>>>> theirs",
    ]


def test_merge_hooks_conflict_survives_yaml_round_trip(tmp_path: Path) -> None:
    """Marker entries in the merged hooks must round-trip through PyYAML untouched.

    Callers (update.py) write the merge result to rebake.yaml and the next
    update reads it back. Conflict markers must survive that round trip so
    re-running rebake update keeps surfacing the conflict (or sees the
    resolved version once the user has edited the markers away).
    """
    base: dict[str, list[str]] = {"post-update": ["echo a"]}
    theirs: dict[str, list[str]] = {"post-update": ["echo theirs"]}
    ours: dict[str, list[str]] = {"post-update": ["echo ours"]}

    result = merge_hooks(base=base, theirs=theirs, ours=ours)

    path = tmp_path / "rebake.yaml"
    path.write_text(yaml.dump({"hooks": result.hooks}, sort_keys=False))
    reloaded = yaml.safe_load(path.read_text())

    assert reloaded == {"hooks": result.hooks}
