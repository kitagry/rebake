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

Check whether the project is up-to-date with its template(s). When a repository
tracks [multiple templates](#multiple-templates), every one is checked and the
command reports each; it exits non-zero if any is outdated.

```bash
rebake check [PROJECT_DIR]
```

Exit codes:
- `0` — up-to-date
- `1` — outdated
- `2` — error (e.g. `.cruft.json` not found)

> **User-facing change:** the stdout is now reported per template link
> (`<template> (<target_directory>) is up-to-date.`) instead of the previous
> single `Project is up-to-date.` / `Project is outdated.`. Exit codes are
> unchanged, so CI gates keep working, but scripts that grep this stdout need
> updating.

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
| `--checkout`, `-c` | Branch, tag or commit to follow |

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

Hooks run in the project directory with the following environment variables available:

| Variable | Value |
|---|---|
| `REBAKE_TEMPLATE` | Template repository URL |
| `REBAKE_OLD_COMMIT` | Commit hash before the update |
| `REBAKE_NEW_COMMIT` | Commit hash after the update |
| `REBAKE_PROJECT_DIR` | Absolute path to the repository root |
| `REBAKE_TARGET_DIR` | Absolute path to this template's target directory (`REBAKE_PROJECT_DIR/<target_directory>`) |

For multi-template repositories, hooks run once per template link with the
working directory set to that link's target directory.

#### Non-interactive usage (e.g. from an LLM agent)

`--quiet` is designed for automated workflows where interactive prompts are not possible.

```bash
# Attempt update non-interactively; exit 1 if new variables need values
rebake update --quiet
```

When `--quiet` is used and new variables are found, rebake prints each variable name and its default value to stderr, then exits with code 1.

## Multiple templates

A single repository can track more than one cookiecutter template — for example
a shared CI/config template at the root plus one language scaffold per
sub-directory. Each template link (an entry in the `templates:` list) records
its own `commit` and a `target_directory` (the sub-path its patches apply to).
`rebake check` and `rebake update` operate on every link; `update` applies each
template's diff into its own `target_directory`.

Every link is self-contained: `context`, `checkout`, `skip` and `hooks` are all
per-entry, so each template keeps its own variables and hooks.

Add a link by adding an entry to the `templates:` list in `rebake.yaml`.

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

rebake writes the `templates:` list form (one entry per template link, even
when there is only one):

```yaml
templates:
  - template: https://github.com/owner/cookiecutter-common
    commit: aaa111...
    checkout: main          # optional: branch/tag/commit to track
    context:
      cookiecutter:
        project_name: my-repo
        author: Jane Doe
    skip:                   # optional: file patterns to skip
      - go.sum
      - "*.lock"
    hooks:                  # optional: shell commands to run on update
      pre-update:
        - make lint
      post-update:
        - make fmt
    # target_directory defaults to "." (repository root)
  - template: https://github.com/owner/cookiecutter-go
    commit: bbb222...
    target_directory: api   # this link's patches apply under api/
    context:
      cookiecutter:
        project_name: my-repo
```

`target_directory` is the sub-path within your repository that the link's
patches apply to (defaults to `.`). It is intentionally **not** named
`directory`: cruft's `.cruft.json` uses `directory` for the opposite thing (a
sub-directory *inside the template repo*), so rebake ignores that key on read
and reserves the name.

### Legacy formats (read-only)

For backward compatibility, rebake also reads the older single-template
top-level form and a cruft `.cruft.json` with the same keys. The next
`rebake update` rewrites the file into the `templates:` list form above.

```yaml
template: https://github.com/owner/template
commit: abc123...
checkout: main
context:
  cookiecutter:
    project_name: my-project
```

## Development

```bash
git clone https://github.com/kitagry/rebake
cd rebake
uv sync
uv run pytest
```
