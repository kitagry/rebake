import json
from pathlib import Path
from unittest.mock import patch

import yaml

from rebake.check import CheckResult, check_entries, is_up_to_date


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

    with patch("rebake.check.resolve_template_commit", return_value="abc123"):
        result = is_up_to_date(tmp_path)

    assert result == CheckResult.UP_TO_DATE


def test_outdated_when_commits_differ(tmp_path):
    make_cruft_file(tmp_path, "abc123")

    with patch("rebake.check.resolve_template_commit", return_value="def456"):
        result = is_up_to_date(tmp_path)

    assert result == CheckResult.OUTDATED


def test_resolve_template_commit_called_with_correct_args(tmp_path):
    make_cruft_file(tmp_path, "abc123")

    with patch("rebake.check.resolve_template_commit", return_value="abc123") as mock_fn:
        is_up_to_date(tmp_path)

    mock_fn.assert_called_once_with(
        "https://github.com/owner/template",
        checkout=None,
    )


def test_resolve_template_commit_uses_checkout(tmp_path):
    cruft_data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {}},
        "checkout": "v2",
    }
    (tmp_path / ".cruft.json").write_text(json.dumps(cruft_data))

    with patch("rebake.check.resolve_template_commit", return_value="abc123") as mock_fn:
        is_up_to_date(tmp_path)

    mock_fn.assert_called_once_with(
        "https://github.com/owner/template",
        checkout="v2",
    )


def make_multi_project(tmp_path, commits: list[str]) -> Path:
    data = {
        "templates": [
            {
                "template": f"https://github.com/owner/template{i}",
                "commit": commit,
                "context": {"cookiecutter": {}},
                "target_directory": "." if i == 0 else f"sub{i}",
            }
            for i, commit in enumerate(commits)
        ]
    }
    (tmp_path / "rebake.yaml").write_text(yaml.dump(data, allow_unicode=True))
    return tmp_path


def test_multi_up_to_date_when_all_match(tmp_path):
    make_multi_project(tmp_path, ["aaa", "bbb"])

    with patch("rebake.check.resolve_template_commit", side_effect=["aaa", "bbb"]):
        result = is_up_to_date(tmp_path)

    assert result == CheckResult.UP_TO_DATE


def test_multi_outdated_when_one_differs(tmp_path):
    make_multi_project(tmp_path, ["aaa", "bbb"])

    with patch("rebake.check.resolve_template_commit", side_effect=["aaa", "ccc"]):
        result = is_up_to_date(tmp_path)

    assert result == CheckResult.OUTDATED


def test_check_entries_reports_each_template(tmp_path):
    make_multi_project(tmp_path, ["aaa", "bbb"])

    with patch("rebake.check.resolve_template_commit", side_effect=["aaa", "ccc"]):
        checks = check_entries(tmp_path)

    assert len(checks) == 2
    assert checks[0].result == CheckResult.UP_TO_DATE
    assert checks[1].result == CheckResult.OUTDATED
    assert checks[1].entry.target_directory == "sub1"
    assert checks[1].head_commit == "ccc"
