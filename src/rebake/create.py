from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from cookiecutter.config import get_user_config
from cookiecutter.generate import generate_context, generate_files
from cookiecutter.prompt import prompt_for_config
from cookiecutter.repository import determine_repo_dir

from rebake.config import CruftConfig
from rebake.utils.git import get_template_head_commit
from rebake.utils.recipe import Recipe, load_recipe


def cookiecutter_interactive(
    template: str,
    output_dir: Path,
    checkout: str | None = None,
) -> tuple[str, dict[str, Any], Recipe]:
    """Run cookiecutter interactively.

    Returns (rendered_project_path, cookiecutter_context, recipe) so callers
    can persist both the answered values and the template-side recipe hooks
    without re-cloning the template.
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

    # Read the recipe from the cloned template before cookiecutter cleans it up.
    recipe = load_recipe(Path(repo_dir))

    if cleanup:
        from cookiecutter.utils import rmtree

        rmtree(repo_dir)

    # Strip private cookiecutter keys (prefixed with _) before saving
    public_context = {k: v for k, v in context["cookiecutter"].items() if not k.startswith("_")}
    return result, public_context, recipe


def run_create(
    template: str,
    output_dir: Path = Path("."),
    checkout: str | None = None,
) -> Path:
    """Create a new project from a cookiecutter template and write rebake.yaml."""
    output_dir = output_dir.resolve()

    commit = get_template_head_commit(template, checkout=checkout)
    rendered_path_str, context, recipe = cookiecutter_interactive(template, output_dir, checkout=checkout)
    rendered_project = Path(rendered_path_str)

    config = CruftConfig(
        template=template,
        commit=commit,
        context={"cookiecutter": context},
        checkout=checkout,
        # TODO: replace this cast by changing CruftConfig.hooks to HookSpec
        # (or a shared type) so the two no longer disagree at the type level.
        hooks=cast("dict[str, list[str]]", recipe.hooks),
    )
    config.save(rendered_project)

    return rendered_project
