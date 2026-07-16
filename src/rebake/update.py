from __future__ import annotations

import tempfile
from pathlib import Path

from rich.console import Console

from rebake.config import CruftConfig, RebakeConfig
from rebake.hooks import run_hooks
from rebake.utils.git import (
    apply_patch,
    clone_at_commit,
    generate_diff,
    get_template_head_commit,
    is_working_tree_clean,
)
from rebake.utils.template import render_template
from rebake.utils.variables import detect_new_variables, prompt_new_variables

console = Console()


def run_update(
    project_dir: Path = Path("."),
    *,
    allow_untracked_files: bool = False,
    quiet: bool = False,
    checkout: str | None = None,
) -> None:
    """Apply the latest template changes to every registered template link.

    Raises RuntimeError when the working tree has uncommitted changes.
    Raises RuntimeError in quiet mode when new template variables are found.
    """
    # Resolve to absolute path before any subprocess/cookiecutter calls that may change CWD
    project_dir = project_dir.resolve()

    if not is_working_tree_clean(project_dir, allow_untracked_files=allow_untracked_files):
        raise RuntimeError("Project has uncommitted changes. Please commit or stash them before updating.")

    config = RebakeConfig.load(project_dir)

    if checkout is not None:
        _apply_checkout_override(config, checkout)

    for entry in config.templates:
        _update_entry(entry, project_dir, config, quiet=quiet)


def _apply_checkout_override(config: RebakeConfig, checkout: str) -> None:
    """Apply a CLI ``--checkout`` override to ``config`` in place.

    Single-template: the value is the ref for the sole link.
    Multi-template: the value must be ``<name>@<ref>`` and overrides only the
    link whose ``name`` matches; per-entry ``checkout:`` in rebake.yaml is left
    untouched.
    """
    if len(config.templates) == 1:
        config.templates[0].checkout = checkout
        return

    name, sep, ref = checkout.partition("@")
    if not sep or not name or not ref:
        raise RuntimeError(
            "--checkout is ambiguous for a multi-template repository. "
            "Use `<name>@<ref>` (e.g. go@main) to target one link, or set `checkout:` per entry in rebake.yaml."
        )
    config.find_by_name(name).checkout = ref


def _update_entry(
    entry: CruftConfig,
    project_dir: Path,
    config: RebakeConfig,
    *,
    quiet: bool,
) -> None:
    target = project_dir / entry.target_directory
    # A hand-added entry may reference a directory that does not exist yet; create
    # it so apply_patch's `git rev-parse` (run from target) does not fail obscurely.
    target.mkdir(parents=True, exist_ok=True)
    old_commit = entry.commit
    new_commit = get_template_head_commit(entry.template, checkout=entry.checkout)

    console.print(
        f"Updating [bold]{entry.template}[/bold] ({entry.target_directory}): "
        f"[cyan]{old_commit[:8]}[/cyan] → [cyan]{new_commit[:8]}[/cyan]"
    )

    old_context = entry.context.get("cookiecutter", {})

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Clone template at old and new commits to compute the diff
        old_template_dir = tmp / "old_template"
        new_template_dir = tmp / "new_template"
        clone_at_commit(entry.template, old_commit, old_template_dir)
        clone_at_commit(entry.template, new_commit, new_template_dir)

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

        # Render both template versions with the merged context
        old_output = tmp / "old_output"
        new_output = tmp / "new_output"
        old_output.mkdir()
        new_output.mkdir()
        old_rendered = render_template(old_template_dir, merged_context, old_output)
        new_rendered = render_template(new_template_dir, merged_context, new_output)

        patch = generate_diff(old_rendered, new_rendered)

    hook_env = {
        "REBAKE_TEMPLATE": entry.template,
        "REBAKE_OLD_COMMIT": old_commit,
        "REBAKE_NEW_COMMIT": new_commit,
        "REBAKE_PROJECT_DIR": str(project_dir),
        "REBAKE_TARGET_DIR": str(target),
    }
    run_hooks("pre-update", target, entry.hooks.get("pre-update", []), env=hook_env)

    if patch:
        success, stderr = apply_patch(patch, target)
        if not success:
            rej_files = sorted(target.rglob("*.rej"))
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
    # Save after each entry so a partial run (or a mid-loop abort) still starts
    # the next run from the new baseline rather than re-applying the same diff.
    entry.commit = new_commit
    entry.context["cookiecutter"] = merged_context
    config.save(project_dir)

    run_hooks("post-update", target, entry.hooks.get("post-update", []), env=hook_env)
