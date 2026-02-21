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
rebake update [PROJECT_DIR]
```

rebake will:
1. Abort if there are uncommitted changes (commit or stash first)
2. Detect new variables added to the template and prompt for their values
3. Generate a diff between the old and new rendered templates
4. Apply the diff with `git apply --reject` — applicable hunks are written immediately; unresolvable hunks are saved as `.rej` files for manual resolution
5. Update `.cruft.json` with the new commit hash and any newly added variables

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

## `.cruft.json` format

```json
{
  "template": "https://github.com/owner/template",
  "commit": "abc123...",
  "checkout": "main",
  "context": {
    "cookiecutter": {
      "project_name": "my-project",
      "author": "Jane Doe"
    }
  },
  "skip": ["go.sum", "*.lock"]
}
```

## Development

```bash
git clone https://github.com/kitagry/rebake
cd rebake
uv sync
uv run pytest
```
