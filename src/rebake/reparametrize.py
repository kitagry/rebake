from __future__ import annotations

import tempfile
from pathlib import Path

from rich.console import Console

from rebake.config import RebakeConfig
from rebake.utils.git import (
    apply_patch,
    clone_at_commit,
    generate_diff,
    is_working_tree_clean,
)
from rebake.utils.template import render_template
from rebake.utils.variables import prompt_all_variables

console = Console()


def run_reparametrize(project_dir: Path = Path("."), *, allow_untracked_files: bool = False) -> None:
    """Change template variables and re-apply the diff.

    Raises RuntimeError when the working tree has uncommitted changes.
    """
    project_dir = project_dir.resolve()

    if not is_working_tree_clean(project_dir, allow_untracked_files=allow_untracked_files):
        raise RuntimeError("Project has uncommitted changes. Please commit or stash them before reparametrizing.")

    config = RebakeConfig.load(project_dir)
    if len(config.templates) != 1:
        raise RuntimeError(
            "reparametrize supports single-template repositories only. "
            "Edit context values in rebake.yaml directly for multi-template repos."
        )
    entry = config.templates[0]
    old_context = entry.context.get("cookiecutter", {})

    console.print("[cyan]Current variables (Enter to keep):[/cyan]")
    new_context = prompt_all_variables(old_context)

    if new_context == old_context:
        console.print("[green]✓[/green] No changes.")
        return

    target = project_dir / entry.directory

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        template_dir = tmp / "template"
        clone_at_commit(entry.template, entry.commit, template_dir)

        old_output = tmp / "old"
        new_output = tmp / "new"
        old_output.mkdir()
        new_output.mkdir()
        old_rendered = render_template(template_dir, old_context, old_output)
        new_rendered = render_template(template_dir, new_context, new_output)

        patch = generate_diff(old_rendered, new_rendered)

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

    entry.context["cookiecutter"] = new_context
    config.save(project_dir)
