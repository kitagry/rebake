import json
from pathlib import Path
from unittest.mock import patch

from rebake.check import CheckResult, is_up_to_date


def make_cruft_file(tmp_path, commit: str) -> Path:
    cruft_data = {
        "template": "https://github.com/owner/template",
        "commit": commit,
        "context": {"cookiecutter": {"project_name": "my-project"}},
    }
    (tmp_path / ".cruft.json").write_text(json.dumps(cruft_data))
    return tmp_path


def test_up_to_date_when_commits_match(tmp_path):
    make_cruft_file(tmp_path, "abc123")

    with patch("rebake.check.get_template_head_commit", return_value="abc123"):
        result = is_up_to_date(tmp_path)

    assert result == CheckResult.UP_TO_DATE


def test_outdated_when_commits_differ(tmp_path):
    make_cruft_file(tmp_path, "abc123")

    with patch("rebake.check.get_template_head_commit", return_value="def456"):
        result = is_up_to_date(tmp_path)

    assert result == CheckResult.OUTDATED


def test_get_template_head_commit_called_with_correct_args(tmp_path):
    make_cruft_file(tmp_path, "abc123")

    with patch("rebake.check.get_template_head_commit", return_value="abc123") as mock_fn:
        is_up_to_date(tmp_path)

    mock_fn.assert_called_once_with(
        "https://github.com/owner/template",
        checkout=None,
    )


def test_get_template_head_commit_uses_checkout(tmp_path):
    cruft_data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {}},
        "checkout": "v2",
    }
    (tmp_path / ".cruft.json").write_text(json.dumps(cruft_data))

    with patch("rebake.check.get_template_head_commit", return_value="abc123") as mock_fn:
        is_up_to_date(tmp_path)

    mock_fn.assert_called_once_with(
        "https://github.com/owner/template",
        checkout="v2",
    )
