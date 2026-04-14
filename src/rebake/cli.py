from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from rebake.check import CheckResult, is_up_to_date

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
    """Check if the project is up-to-date with its template."""
    try:
        result = is_up_to_date(project_dir)
    except FileNotFoundError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=2)

    if result == CheckResult.UP_TO_DATE:
        console.print("[green]✓[/green] Project is up-to-date.")
        raise typer.Exit(code=0)
    else:
        console.print("[yellow]![/yellow] Project is outdated.")
        raise typer.Exit(code=1)


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
) -> None:
    """Apply the latest template changes to the project."""
    from rebake.update import run_update

    try:
        run_update(project_dir, allow_untracked_files=allow_untracked_files)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
