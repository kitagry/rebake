from __future__ import annotations

import shutil
import tempfile
from collections.abc import Sequence
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


def _reject_unsafe_target(target_directory: str) -> None:
    """Reject an absolute or parent-escaping target before rendering starts.

    This is a purely syntactic pre-check (any ``..`` component or an absolute
    path), so it is deliberately stricter than ``run_add``'s post-resolve
    ``is_relative_to`` guard: an in-repo path like ``a/../b`` is accepted by
    ``run_add`` but rejected here. Running before the primary template is rendered
    lets ``run_create`` reject an unsafe target without leaving a half-built
    project on disk. It does not guard against a later render *failing* midway —
    that leaves the already-rendered links in place, just as a bare ``rebake add``
    would.
    """
    path = Path(target_directory)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"target_directory {target_directory!r} must be a relative path inside the project.")


def run_create(
    template: str,
    output_dir: Path = Path("."),
    checkout: str | None = None,
    additional: Sequence[tuple[str, str]] | None = None,
) -> Path:
    """Create a new project from a cookiecutter template and write rebake.yaml.

    ``additional`` registers extra template links, each a ``(template,
    target_directory)`` pair rendered into the new project after the primary one
    via ``run_add`` (cookiecutter's wrapper is stripped and the entry is appended
    to rebake.yaml). Passing them here is equivalent to a ``create`` followed by
    one ``add`` per pair. Links may share a ``target_directory`` (typically
    ``"."``); on a path collision the later link wins on disk, mirroring
    ``update``'s later-entry-wins ordering.
    """
    for _, target_directory in additional or []:
        _reject_unsafe_target(target_directory)

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

    for add_template, target_directory in additional or []:
        run_add(add_template, project_dir=rendered_project, target_directory=target_directory)

    return rendered_project


def run_add(
    template: str,
    project_dir: Path = Path("."),
    target_directory: str = ".",
    checkout: str | None = None,
) -> TemplateEntry:
    """Render an additional template into ``project_dir/target_directory`` and register it.

    Appends an entry to the repository's root ``rebake.yaml`` (creating the file
    when absent). cookiecutter always renders inside a top-level project folder;
    that wrapper is stripped so the template's files land directly under
    ``target_directory``.
    """
    project_dir = project_dir.resolve()
    target = project_dir / target_directory
    # The entry must live under the repository: reject a target that is outside
    # project_dir (e.g. `-t ../foo` or an absolute path), which a later `update`
    # would otherwise re-render outside project_dir.
    if not target.resolve().is_relative_to(project_dir):
        raise ValueError(f"target_directory {target_directory!r} is outside the repository root {project_dir}.")

    # Load (or start) the config before writing anything. A missing
    # rebake.yaml/.cruft.json starts a fresh config; an existing but malformed
    # file raises here (ValueError, intentionally left to propagate) before any
    # rendered files land on disk, so a failed add leaves no orphaned files.
    try:
        config = RebakeConfig.load(project_dir)
    except FileNotFoundError:
        config = RebakeConfig(templates=[])

    commit = resolve_template_commit(template, checkout=checkout)

    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        rendered_path_str, context = cookiecutter_interactive(template, Path(tmpdir), checkout=checkout)
        # Strip the cookiecutter project-name wrapper: copy its contents into target.
        shutil.copytree(rendered_path_str, target, dirs_exist_ok=True)

    entry = TemplateEntry(
        template=template,
        commit=commit,
        context={"cookiecutter": context},
        checkout=checkout,
        target_directory=target_directory,
    )
    config.templates.append(entry)
    config.save(project_dir)

    return entry
