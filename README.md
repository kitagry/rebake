# rebake

A spiritual successor to [cruft](https://github.com/cruft/cruft) for managing [cookiecutter](https://github.com/cookiecutter/cookiecutter) projects.

rebake improves on cruft in two key areas:

1. **Partial apply on conflict** — uses `git apply --reject` to apply all applicable hunks; only the unresolvable portions are saved as `.rej` files
2. **New variable detection** — prompts for variables added to the template since the project was last updated

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Git

## Quick Start

```bash
uvx rebake check
uvx rebake update
```

> No installation required. Uses [uv](https://docs.astral.sh/uv/).

## Installation

To install permanently:

```bash
uv tool install rebake
```

Or add it to a project:

```bash
uv add rebake
```

## Usage

### `rebake check`

Check whether the project is up-to-date with its template.

```bash
rebake check [PROJECT_DIR]
```

Exit codes:
- `0` — up-to-date
- `1` — outdated
- `2` — error (e.g. `.cruft.json` not found)

### `rebake update`

Apply the latest template changes to the project.

```bash
rebake update [PROJECT_DIR] [OPTIONS]
```

rebake will:
1. Abort if there are uncommitted changes (commit or stash first)
2. Run `pre-update` hooks (if defined) — abort if any hook fails
3. Detect new variables added to the template and prompt for their values
4. Generate a diff between the old and new rendered templates
5. Apply the diff with `git apply --reject` — applicable hunks are written immediately; unresolvable hunks are saved as `.rej` files for manual resolution
6. Update `rebake.yaml` with the new commit hash and any newly added variables
7. Run `post-update` hooks (if defined)

#### Options

| Option | Description |
|---|---|
| `--allow-untracked-files` | Allow update even if untracked files exist (no other changes) |
| `--quiet` | Disable interactive prompts; exit 1 if new variables are found without a supplied value |

#### Hooks

Define shell commands to run before or after the update in `rebake.yaml`:

```yaml
hooks:
  pre-update:
    - make lint          # runs before the patch is applied; abort on failure
  post-update:
    - go generate ./...  # runs after rebake.yaml is saved; abort on failure
    - make fmt
```

A template author can also seed these hooks once on the template side via `rebake-recipe.yaml` (see [Authoring a template](#authoring-a-template) below). On `rebake update`, recipe-defined hooks are 3-way merged into `rebake.yaml.hooks` so upstream additions appear automatically while project-specific entries are preserved. If both the recipe and the user edit the same lines, update writes git-style conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) directly into `rebake.yaml.hooks`, skips the patch / hook execution, and exits non-zero. Resolve the markers, commit, then re-run `rebake update`.

Hooks run in the project directory with the following environment variables available:

| Variable | Value |
|---|---|
| `REBAKE_TEMPLATE` | Template repository URL |
| `REBAKE_OLD_COMMIT` | Commit hash before the update |
| `REBAKE_NEW_COMMIT` | Commit hash after the update |
| `REBAKE_PROJECT_DIR` | Absolute path to the project directory |

#### Non-interactive usage (e.g. from an LLM agent)

`--quiet` is designed for automated workflows where interactive prompts are not possible.

```bash
# Attempt update non-interactively; exit 1 if new variables need values
rebake update --quiet
```

When `--quiet` is used and new variables are found, rebake prints each variable name and its default value to stderr, then exits with code 1.

## Authoring a template

Template authors can ship default hooks alongside the template by adding a `rebake-recipe.yaml` file at the template repository root:

```yaml
# rebake-recipe.yaml (lives in the template repo, not in generated projects)
hooks:
  pre-update:
    - make fmt
  post-update:
    - go generate ./...
```

- On `rebake create`, the recipe's hooks are copied into the generated project's `rebake.yaml.hooks` verbatim.
- On `rebake update`, the recipe at the new template commit is 3-way merged into `rebake.yaml.hooks` (with the previous commit's recipe as the base). Upstream additions flow through automatically; user-added entries are preserved.
- Conflicting edits (the recipe and the user changed the same hook line to different values) cause `rebake update` to write git-style conflict markers into `rebake.yaml.hooks` and exit non-zero. The patch and the hook commands themselves are skipped; the user resolves the markers in `rebake.yaml`, commits, then re-runs `rebake update`.

Only `hooks.pre-update` and `hooks.post-update` are recognized today. Templates without a `rebake-recipe.yaml` are unaffected.

## Migrating from cruft

rebake reads `.cruft.json` as-is. No migration needed — just replace `cruft` with `rebake` in your commands.

```bash
# before
cruft check
cruft update

# after
rebake check
rebake update
```

## `rebake.yaml` format

```yaml
template: https://github.com/owner/template
commit: abc123...
checkout: main          # optional: branch/tag/commit to track
context:
  cookiecutter:
    project_name: my-project
    author: Jane Doe
skip:                   # optional: file patterns to skip
  - go.sum
  - "*.lock"
hooks:                  # optional: shell commands to run on update
  pre-update:
    - make lint
  post-update:
    - make fmt
```

## Development

```bash
git clone https://github.com/kitagry/rebake
cd rebake
uv sync
uv run pytest
```
