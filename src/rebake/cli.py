from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from rebake.check import CheckResult, check_entries

app = typer.Typer(help="A spiritual successor to cruft for managing cookiecutter projects.")
console = Console()
err_console = Console(stderr=True)


@app.command()
def create(
    template: str = typer.Argument(..., help="URL or path to the cookiecutter template"),
    output_dir: Path = typer.Option(Path("."), "--output-dir", "-o", help="Directory to create the project in"),
    checkout: str | None = typer.Option(None, "--checkout", help="Branch, tag or commit to use"),
) -> None:
    """Create a new project from a cookiecutter template."""
    from rebake.create import run_create

    try:
        project = run_create(template, output_dir=output_dir, checkout=checkout)
        console.print(f"[green]✓[/green] Project created at [bold]{project}[/bold]")
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command()
def check(
    project_dir: Path = typer.Argument(Path("."), help="Path to the project directory"),
) -> None:
    """Check if every registered template link is up-to-date."""
    try:
        checks = check_entries(project_dir)
    except (FileNotFoundError, ValueError) as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=2)

    outdated = [c for c in checks if c.result == CheckResult.OUTDATED]
    for c in checks:
        if c.result == CheckResult.UP_TO_DATE:
            console.print(f"[green]✓[/green] {c.entry.template} ({c.entry.target_directory}) is up-to-date.")
        else:
            console.print(
                f"[yellow]![/yellow] {c.entry.template} ({c.entry.target_directory}) is outdated: "
                f"[cyan]{c.entry.commit[:8]}[/cyan] → [cyan]{c.head_commit[:8]}[/cyan]"
            )
    raise typer.Exit(code=1 if outdated else 0)


@app.command()
def reparametrize(
    project_dir: Path = typer.Argument(Path("."), help="Path to the project directory"),
    allow_untracked_files: bool = typer.Option(
        False,
        "--allow-untracked-files",
        help="Allow reparametrize even if there are untracked files in the git repository (but no other changes)",
    ),
) -> None:
    """Change template variables and re-apply the diff."""
    from rebake.reparametrize import run_reparametrize

    try:
        run_reparametrize(project_dir, allow_untracked_files=allow_untracked_files)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command()
def update(
    project_dir: Path = typer.Argument(Path("."), help="Path to the project directory"),
    allow_untracked_files: bool = typer.Option(
        False,
        "--allow-untracked-files",
        help="Allow the project's cruft to be updated if there are untracked files in the git repository"
        " (but no other changes)",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        help="Do not prompt for new variables; exit 1 if any new variables are found without a supplied value.",
    ),
    checkout: str | None = typer.Option(
        None,
        "--checkout",
        "-c",
        help="Branch, tag or commit to follow.",
    ),
) -> None:
    """Apply the latest template changes to the project."""
    from rebake.update import run_update

    try:
        run_update(project_dir, allow_untracked_files=allow_untracked_files, quiet=quiet, checkout=checkout)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
