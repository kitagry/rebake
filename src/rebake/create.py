from __future__ import annotations

from pathlib import Path
from typing import Any

from cookiecutter.config import get_user_config
from cookiecutter.generate import generate_context, generate_files
from cookiecutter.prompt import prompt_for_config
from cookiecutter.repository import determine_repo_dir

from rebake.config import RebakeConfig, TemplateEntry
from rebake.utils.git import resolve_template_commit


def cookiecutter_interactive(
    template: str,
    output_dir: Path,
    checkout: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Run cookiecutter interactively.

    Returns (rendered_project_path, cookiecutter_context) so callers can
    persist the answered values in rebake.yaml without a second prompt.
    """
    config_dict = get_user_config()
    repo_dir, cleanup = determine_repo_dir(
        template=template,
        abbreviations=config_dict["abbreviations"],
        clone_to_dir=config_dict["cookiecutters_dir"],
        checkout=checkout,
        no_input=False,
        password=None,
        directory=None,
    )

    context = generate_context(
        context_file=str(Path(repo_dir) / "cookiecutter.json"),
        default_context=config_dict["default_context"],
    )
    # prompt_for_config fills in values interactively
    answered: dict[str, Any] = prompt_for_config(context, no_input=False)
    context["cookiecutter"].update(answered)

    result = generate_files(
        repo_dir=repo_dir,
        context=context,
        output_dir=str(output_dir),
        overwrite_if_exists=False,
    )

    if cleanup:
        from cookiecutter.utils import rmtree

        rmtree(repo_dir)

    # Strip private cookiecutter keys (prefixed with _) before saving
    public_context = {k: v for k, v in context["cookiecutter"].items() if not k.startswith("_")}
    return result, public_context


def run_create(
    template: str,
    output_dir: Path = Path("."),
    checkout: str | None = None,
) -> Path:
    """Create a new project from a cookiecutter template and write rebake.yaml."""
    output_dir = output_dir.resolve()

    commit = resolve_template_commit(template, checkout=checkout)
    rendered_path_str, context = cookiecutter_interactive(template, output_dir, checkout=checkout)
    rendered_project = Path(rendered_path_str)

    entry = TemplateEntry(
        template=template,
        commit=commit,
        context={"cookiecutter": context},
        checkout=checkout,
    )
    RebakeConfig(templates=[entry]).save(rendered_project)

    return rendered_project
