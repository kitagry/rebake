from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from rebake.check import CheckResult, is_up_to_date

app = typer.Typer(help="A spiritual successor to cruft for managing cookiecutter projects.")
console = Console()
err_console = Console(stderr=True)


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
def update(
    project_dir: Path = typer.Argument(Path("."), help="Path to the project directory"),
) -> None:
    """Apply the latest template changes to the project."""
    from rebake.update import run_update

    try:
        run_update(project_dir)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
