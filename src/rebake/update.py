from __future__ import annotations

import tempfile
from pathlib import Path

from rich.console import Console

from rebake.config import CruftConfig
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


def run_update(project_dir: Path = Path(".")) -> None:
    """Apply the latest template changes to the project.

    Raises RuntimeError when the working tree has uncommitted changes.
    """
    # Resolve to absolute path before any subprocess/cookiecutter calls that may change CWD
    project_dir = project_dir.resolve()

    if not is_working_tree_clean(project_dir):
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
        extra_context = {}
        if new_vars:
            console.print("[yellow]New template variables detected. Please provide values:[/yellow]")
            extra_context = prompt_new_variables(new_vars)

        merged_context = {**old_context, **extra_context}

        # Render both template versions with the merged context
        old_output = tmp / "old_output"
        new_output = tmp / "new_output"
        old_output.mkdir()
        new_output.mkdir()
        old_rendered = render_template(old_template_dir, merged_context, old_output)
        new_rendered = render_template(new_template_dir, merged_context, new_output)

        patch = generate_diff(old_rendered, new_rendered)

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
