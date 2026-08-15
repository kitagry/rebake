"""End-to-end specification for template-side recipe hooks.

Recipe hooks defined in the template's rebake-recipe.yaml are merged into
the generated project's rebake.yaml.hooks. On update, a 3-way merge keeps
user additions while bringing in upstream changes.

Most tests are marked xfail(strict=True) until the implementation lands.
The follow-up PRs in the stack wire the recipe loader, merge utility, and
create/update plumbing, then remove these xfail markers.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from rebake.cli import app

runner = CliRunner()


# Marker reused on every unimplemented test; the explicit reason makes it
# easy to grep for when removing in the final integration PR.
xfail_until_implemented = pytest.mark.xfail(
    strict=True,
    reason="recipe hooks not yet wired",
)


def _head_commit(repo: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _render_project(template_repo: Path, output_dir: Path) -> Path:
    """Render the template into output_dir and return the rendered project path."""
    output_dir.mkdir(exist_ok=True)
    result = runner.invoke(
        app,
        ["create", str(template_repo), "--output-dir", str(output_dir)],
        input="my-project\n",
    )
    assert result.exit_code == 0, result.output
    return output_dir / "my-project"


def _init_git(project_dir: Path) -> None:
    subprocess.run(["git", "init"], cwd=project_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project_dir, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=project_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=project_dir, capture_output=True, check=True)


def _write_recipe(template_repo: Path, recipe: dict) -> None:
    """Overwrite rebake-recipe.yaml in the template and commit the change."""
    (template_repo / "rebake-recipe.yaml").write_text(yaml.dump(recipe, sort_keys=False))
    subprocess.run(["git", "add", "."], cwd=template_repo, check=True)
    subprocess.run(["git", "commit", "-m", "update recipe"], cwd=template_repo, check=True)


def _set_user_hooks(project_dir: Path, hooks: dict) -> None:
    """Edit rebake.yaml.hooks in the generated project (simulating a user edit)."""
    data = yaml.safe_load((project_dir / "rebake.yaml").read_text())
    data["hooks"] = hooks
    (project_dir / "rebake.yaml").write_text(yaml.dump(data, allow_unicode=True, sort_keys=False))


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@xfail_until_implemented
def test_create_merges_recipe_into_hooks(tmp_path: Path, template_repo_with_recipe: Path) -> None:
    """rebake create copies the recipe's hooks into rebake.yaml.hooks verbatim.

    Given:
      template_with_recipe fixture with a rebake-recipe.yaml that declares both
      pre-update and post-update hooks.

    When:
      rebake create runs against the template.

    Then:
      The generated rebake.yaml lists those hooks under `hooks` (the same field
      a user would edit by hand). No separate template_hooks field exists.
    """
    project = _render_project(template_repo_with_recipe, tmp_path / "output")
    commit = _head_commit(template_repo_with_recipe)

    data = yaml.safe_load((project / "rebake.yaml").read_text())

    assert data == {
        "template": str(template_repo_with_recipe),
        "commit": commit,
        "context": {"cookiecutter": {"project_name": "my-project"}},
        "hooks": {
            "pre-update": ['echo "template pre" > "$REBAKE_PROJECT_DIR/template_pre.log"'],
            "post-update": ['echo "template post: $REBAKE_NEW_COMMIT" > "$REBAKE_PROJECT_DIR/template_post.log"'],
        },
    }


@pytest.mark.e2e
def test_create_without_recipe_keeps_hooks_empty(tmp_path: Path, template_repo: Path) -> None:
    """A template with no rebake-recipe.yaml produces a rebake.yaml without hooks.

    Given:
      simple_template fixture (no rebake-recipe.yaml).

    When:
      rebake create runs.

    Then:
      The generated rebake.yaml contains only the existing core fields
      (template / commit / context). Backwards compatible.
    """
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    result = runner.invoke(
        app,
        ["create", str(template_repo), "--output-dir", str(output_dir)],
        input="my-project\n",
    )
    assert result.exit_code == 0, result.output
    commit = _head_commit(template_repo)

    data = yaml.safe_load((output_dir / "my-project" / "rebake.yaml").read_text())

    assert data == {
        "template": str(template_repo),
        "commit": commit,
        "context": {"cookiecutter": {"project_name": "my-project"}},
    }


# ---------------------------------------------------------------------------
# update — clean 3-way merge
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@xfail_until_implemented
def test_update_clean_merge_keeps_user_additions(tmp_path: Path, template_repo_with_recipe: Path) -> None:
    """User-added hooks survive update; upstream changes are picked up alongside.

    Given:
      A project created from the fixture. The user adds a post-update entry
      that did not exist in the recipe. The template's recipe is then bumped
      to change the pre-update command. The two edits touch different events,
      so the per-event 3-way merge does not conflict.

    When:
      rebake update runs.

    Then:
      rebake.yaml.hooks.pre-update has the bumped recipe entry, and
      rebake.yaml.hooks.post-update keeps both the original recipe entry and
      the user-added entry. Clean 3-way merge, no manual intervention.
    """
    project = _render_project(template_repo_with_recipe, tmp_path / "output")

    _set_user_hooks(
        project,
        {
            "pre-update": ['echo "template pre" > "$REBAKE_PROJECT_DIR/template_pre.log"'],
            "post-update": [
                'echo "template post: $REBAKE_NEW_COMMIT" > "$REBAKE_PROJECT_DIR/template_post.log"',
                'echo "user added" > "$REBAKE_PROJECT_DIR/user.log"',
            ],
        },
    )
    _init_git(project)

    bumped_recipe = {
        "hooks": {
            "pre-update": ['echo "template pre v2" > "$REBAKE_PROJECT_DIR/template_pre.log"'],
            "post-update": [
                'echo "template post: $REBAKE_NEW_COMMIT" > "$REBAKE_PROJECT_DIR/template_post.log"',
            ],
        }
    }
    _write_recipe(template_repo_with_recipe, bumped_recipe)
    new_commit = _head_commit(template_repo_with_recipe)

    result = runner.invoke(app, ["update", str(project)])
    assert result.exit_code == 0, result.output

    data = yaml.safe_load((project / "rebake.yaml").read_text())

    assert data == {
        "template": str(template_repo_with_recipe),
        "commit": new_commit,
        "context": {"cookiecutter": {"project_name": "my-project"}},
        "hooks": {
            "pre-update": ['echo "template pre v2" > "$REBAKE_PROJECT_DIR/template_pre.log"'],
            "post-update": [
                'echo "template post: $REBAKE_NEW_COMMIT" > "$REBAKE_PROJECT_DIR/template_post.log"',
                'echo "user added" > "$REBAKE_PROJECT_DIR/user.log"',
            ],
        },
    }


@pytest.mark.e2e
@xfail_until_implemented
def test_update_clean_merge_picks_up_recipe_additions(tmp_path: Path, template_repo_with_recipe: Path) -> None:
    """A brand-new recipe entry appears in rebake.yaml.hooks after update.

    Given:
      A project created from the fixture (user has NOT edited hooks). The
      template's recipe is then extended with a brand-new post-update entry
      that did not exist before.

    When:
      rebake update runs.

    Then:
      rebake.yaml.hooks.post-update contains both the original and the new
      recipe entries.
    """
    project = _render_project(template_repo_with_recipe, tmp_path / "output")
    _init_git(project)

    extended_recipe = {
        "hooks": {
            "pre-update": ['echo "template pre" > "$REBAKE_PROJECT_DIR/template_pre.log"'],
            "post-update": [
                'echo "template post: $REBAKE_NEW_COMMIT" > "$REBAKE_PROJECT_DIR/template_post.log"',
                'echo "second hook" > "$REBAKE_PROJECT_DIR/second.log"',
            ],
        }
    }
    _write_recipe(template_repo_with_recipe, extended_recipe)
    new_commit = _head_commit(template_repo_with_recipe)

    result = runner.invoke(app, ["update", str(project)])
    assert result.exit_code == 0, result.output

    data = yaml.safe_load((project / "rebake.yaml").read_text())

    assert data == {
        "template": str(template_repo_with_recipe),
        "commit": new_commit,
        "context": {"cookiecutter": {"project_name": "my-project"}},
        "hooks": {
            "pre-update": ['echo "template pre" > "$REBAKE_PROJECT_DIR/template_pre.log"'],
            "post-update": [
                'echo "template post: $REBAKE_NEW_COMMIT" > "$REBAKE_PROJECT_DIR/template_post.log"',
                'echo "second hook" > "$REBAKE_PROJECT_DIR/second.log"',
            ],
        },
    }


# ---------------------------------------------------------------------------
# update — conflict
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@xfail_until_implemented
def test_update_conflict_writes_markers_and_skips_patch(tmp_path: Path, template_repo_with_recipe: Path) -> None:
    """When user and template both edit the same hook line, update writes markers
    into rebake.yaml.hooks and skips everything else.

    Given:
      A project created from the fixture. The user rewrites the recipe-derived
      post-update entry to something different. The template's recipe also
      rewrites that entry to a third different value (different from both the
      original and the user's version).

    When:
      rebake update runs.

    Then:
      - The command exits non-zero.
      - rebake.yaml.hooks.post-update contains git-style conflict markers as
        plain list entries, so the user can resolve them in place.
      - rebake.yaml.commit is advanced to the new template commit (so that
        resolving the markers and re-running update picks up cleanly instead
        of replaying the same conflict).
      - Other events (pre-update) are merged cleanly and reflected.
    """
    project = _render_project(template_repo_with_recipe, tmp_path / "output")
    # The fixture is bumped below; capture the original commit so we can check
    # the bumped commit landed in rebake.yaml.
    _ = _head_commit(template_repo_with_recipe)

    user_hooks = {
        "pre-update": ['echo "template pre" > "$REBAKE_PROJECT_DIR/template_pre.log"'],
        "post-update": ['echo "user rewrite" > "$REBAKE_PROJECT_DIR/template_post.log"'],
    }
    _set_user_hooks(project, user_hooks)
    _init_git(project)

    diverging_recipe = {
        "hooks": {
            "pre-update": ['echo "template pre" > "$REBAKE_PROJECT_DIR/template_pre.log"'],
            "post-update": ['echo "template rewrite" > "$REBAKE_PROJECT_DIR/template_post.log"'],
        }
    }
    _write_recipe(template_repo_with_recipe, diverging_recipe)
    new_commit = _head_commit(template_repo_with_recipe)

    result = runner.invoke(app, ["update", str(project)])
    assert result.exit_code != 0, result.output

    data = yaml.safe_load((project / "rebake.yaml").read_text())

    assert data == {
        "template": str(template_repo_with_recipe),
        "commit": new_commit,
        "context": {"cookiecutter": {"project_name": "my-project"}},
        "hooks": {
            "pre-update": ['echo "template pre" > "$REBAKE_PROJECT_DIR/template_pre.log"'],
            "post-update": [
                "<<<<<<< ours",
                'echo "user rewrite" > "$REBAKE_PROJECT_DIR/template_post.log"',
                "=======",
                'echo "template rewrite" > "$REBAKE_PROJECT_DIR/template_post.log"',
                ">>>>>>> theirs",
            ],
        },
    }
