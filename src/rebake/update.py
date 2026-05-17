from __future__ import annotations

import tempfile
from pathlib import Path
from typing import cast

from rich.console import Console

from rebake.config import CruftConfig
from rebake.hooks import run_hooks
from rebake.utils.git import (
    apply_patch,
    clone_at_commit,
    generate_diff,
    get_template_head_commit,
    is_working_tree_clean,
)
from rebake.utils.recipe import HookSpec, load_recipe, merge_hooks
from rebake.utils.template import render_template
from rebake.utils.variables import detect_new_variables, prompt_new_variables

console = Console()


def run_update(
    project_dir: Path = Path("."),
    *,
    allow_untracked_files: bool = False,
    quiet: bool = False,
) -> None:
    """Apply the latest template changes to the project.

    Raises RuntimeError when the working tree has uncommitted changes.
    Raises RuntimeError in quiet mode when new template variables are found.
    """
    # Resolve to absolute path before any subprocess/cookiecutter calls that may change CWD
    project_dir = project_dir.resolve()

    if not is_working_tree_clean(project_dir, allow_untracked_files=allow_untracked_files):
        raise RuntimeError("Project has uncommitted changes. Please commit or stash them before updating.")

    config = CruftConfig.load(project_dir)
    old_commit = config.commit
    new_commit = get_template_head_commit(config.template, checkout=config.checkout)

    console.print(f"Updating from [cyan]{old_commit[:8]}[/cyan] → [cyan]{new_commit[:8]}[/cyan]")

    old_context = config.context.get("cookiecutter", {})

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Clone template at old and new commits to compute the diff
        old_template_dir = tmp / "old_template"
        new_template_dir = tmp / "new_template"
        clone_at_commit(config.template, old_commit, old_template_dir)
        clone_at_commit(config.template, new_commit, new_template_dir)

        # Detect variables added in the new template and prompt the user
        new_vars = detect_new_variables(new_template_dir, old_context)
        prompted_context: dict[str, str] = {}
        if new_vars:
            if quiet:
                lines = "\n".join(
                    f"  {k}: {v}" if isinstance(v, str) else f"  {k}: (default: {v!r})" for k, v in new_vars.items()
                )
                raise RuntimeError(f"New template variables require values:\n{lines}")
            console.print("[yellow]New template variables detected. Please provide values:[/yellow]")
            prompted_context = prompt_new_variables(new_vars)
        merged_context = {**old_context, **prompted_context}

        # 3-way merge of hooks: base = recipe at old commit, theirs = recipe at
        # new commit, ours = current rebake.yaml.hooks.
        base_hooks = load_recipe(old_template_dir).hooks
        theirs_hooks = load_recipe(new_template_dir).hooks
        ours_hooks = cast(HookSpec, config.hooks)
        merge_result = merge_hooks(base=base_hooks, theirs=theirs_hooks, ours=ours_hooks)

        # On conflict, write the marker-laden hooks (and advance commit:) to
        # rebake.yaml and stop. The patch and hook runs are skipped so the
        # project state stays at the merge boundary. Bumping commit: makes the
        # next update a 2-way merge from the user's resolved hooks against an
        # unchanged theirs — i.e. resolving and re-running picks up cleanly
        # instead of replaying the same conflict.
        # TODO: provide a `rebake update --continue` to apply the patch and
        # run hooks once the user has resolved markers, instead of requiring
        # a full re-run.
        if merge_result.has_conflicts:
            # TODO: replace this cast by aligning CruftConfig.hooks with HookSpec.
            config.hooks = cast("dict[str, list[str]]", merge_result.hooks)
            config.commit = new_commit
            config.context["cookiecutter"] = merged_context
            config.save(project_dir)
            events = ", ".join(f"hooks.{c.event}" for c in merge_result.conflicts)
            console.print(f"[red]✗[/red] Hook merge conflict in [bold]{events}[/bold].")
            console.print(
                "Conflict markers were written to [bold]rebake.yaml[/bold]. "
                "Resolve them, commit, then re-run [bold]rebake update[/bold] to apply the template patch."
            )
            raise RuntimeError(f"Hook merge conflict in {events}")

        # Render both template versions with the merged context
        old_output = tmp / "old_output"
        new_output = tmp / "new_output"
        old_output.mkdir()
        new_output.mkdir()
        old_rendered = render_template(old_template_dir, merged_context, old_output)
        new_rendered = render_template(new_template_dir, merged_context, new_output)

        patch = generate_diff(old_rendered, new_rendered)

    # Adopt the merged hooks so both the upcoming hook runs and the saved
    # rebake.yaml reflect the post-merge state.
    # TODO: replace this cast by aligning CruftConfig.hooks with HookSpec.
    config.hooks = cast("dict[str, list[str]]", merge_result.hooks)

    hook_env = {
        "REBAKE_TEMPLATE": config.template,
        "REBAKE_OLD_COMMIT": old_commit,
        "REBAKE_NEW_COMMIT": new_commit,
        "REBAKE_PROJECT_DIR": str(project_dir),
    }
    run_hooks("pre-update", project_dir, config.hooks.get("pre-update", []), env=hook_env)

    if patch:
        success, stderr = apply_patch(patch, project_dir)
        if not success:
            rej_files = sorted(project_dir.rglob("*.rej"))
            console.print("[yellow]![/yellow] Some hunks could not be applied.")
            if rej_files:
                console.print("Resolve conflicts and delete the following [bold].rej[/bold] files:")
                for f in rej_files:
                    console.print(f"  [bold]{f.relative_to(project_dir)}[/bold]")
            if stderr:
                console.print(stderr)
        else:
            console.print("[green]✓[/green] Patch applied successfully.")
    else:
        console.print("[green]✓[/green] No changes to apply.")

    # Persist the new commit hash and any newly prompted variables.
    # Save even on partial apply so the next run starts from the new baseline
    # rather than re-applying the same diff.
    config.commit = new_commit
    config.context["cookiecutter"] = merged_context
    config.save(project_dir)

    run_hooks("post-update", project_dir, config.hooks.get("post-update", []), env=hook_env)
