from __future__ import annotations

import tempfile
from pathlib import Path

from rich.console import Console

from rebake.config import RebakeConfig, TemplateEntry
from rebake.utils.git import (
    apply_patch,
    clone_at_commit,
    generate_diff,
    is_working_tree_clean,
)
from rebake.utils.template import render_template
from rebake.utils.variables import prompt_all_variables

console = Console()


def run_reparametrize(
    project_dir: Path = Path("."),
    *,
    allow_untracked_files: bool = False,
    name: str | None = None,
) -> None:
    """Change template variables and re-apply the diff for each template link.

    By default every registered template link is reparametrized in turn. Pass
    ``name`` to reparametrize only the link whose ``TemplateEntry.name`` matches.

    Raises RuntimeError when the working tree has uncommitted changes, or when
    ``name`` does not match a named link.
    """
    # Resolve to absolute path before any subprocess/cookiecutter calls that may change CWD
    project_dir = project_dir.resolve()

    if not is_working_tree_clean(project_dir, allow_untracked_files=allow_untracked_files):
        raise RuntimeError("Project has uncommitted changes. Please commit or stash them before reparametrizing.")

    config = RebakeConfig.load(project_dir)

    for entry in _select_entries(config, name):
        _reparametrize_entry(entry, project_dir, config)


def _select_entries(config: RebakeConfig, name: str | None) -> list[TemplateEntry]:
    """Return the template links to reparametrize.

    Without ``name`` every link is selected. With ``name`` only the link whose
    ``name`` matches is selected; unnamed links cannot be targeted by name. This
    mirrors ``update._apply_checkout_override``'s selection philosophy.
    """
    if name is None:
        return config.templates
    return [config.find_by_name(name)]


def _reparametrize_entry(entry: TemplateEntry, project_dir: Path, config: RebakeConfig) -> None:
    old_context = entry.context.get("cookiecutter", {})

    console.print(f"Reparametrizing [bold]{entry.template}[/bold] ({entry.target_directory}):")
    console.print("[cyan]Current variables (Enter to keep):[/cyan]")
    new_context = prompt_all_variables(old_context)

    if new_context == old_context:
        console.print("[green]✓[/green] No changes.")
        return

    target = project_dir / entry.target_directory
    # A hand-added entry may reference a directory that does not exist yet; create
    # it so apply_patch's `git rev-parse` (run from target) does not fail obscurely.
    target.mkdir(parents=True, exist_ok=True)

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

    # Persist the new context. Save after each entry so a partial run (or a
    # mid-loop abort) still persists the entries already processed — mirrors
    # update._update_entry's per-entry save rationale.
    entry.context["cookiecutter"] = dict(new_context)
    config.save(project_dir)
