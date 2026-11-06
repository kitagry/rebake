import re
from pathlib import Path

import pytest
from typer.main import get_command_name

from rebake.cli import app

README = (Path(__file__).parent.parent / "README.md").read_text()

# Typer exposes `def foo_bar` as `foo-bar`, so derive names the same way the CLI does.
COMMANDS = [
    cmd.name or get_command_name(cmd.callback.__name__) for cmd in app.registered_commands if cmd.callback is not None
]


@pytest.mark.parametrize("command", COMMANDS)
def test_every_cli_command_has_a_usage_section(command):
    assert f"### `rebake {command}`" in README


@pytest.mark.parametrize("command", COMMANDS)
def test_every_cli_command_is_listed_in_the_usage_table(command):
    assert f"| [`rebake {command}`](#rebake-{command}) |" in README


def test_readme_documents_no_removed_commands():
    sections = re.findall(r"^### `rebake ([\w-]+)`", README, flags=re.MULTILINE)
    table_rows = re.findall(r"^\| \[`rebake ([\w-]+)`\]", README, flags=re.MULTILINE)

    assert sorted(sections) == sorted(COMMANDS)
    assert sorted(table_rows) == sorted(COMMANDS)
