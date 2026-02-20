import json
import pytest
from pathlib import Path

from rebake.config import CruftConfig


def test_load_basic(tmp_path):
    cruft_data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {"project_name": "my-project"}},
    }
    (tmp_path / ".cruft.json").write_text(json.dumps(cruft_data))

    config = CruftConfig.load(tmp_path)

    assert config.template == "https://github.com/owner/template"
    assert config.commit == "abc123"
    assert config.context == {"cookiecutter": {"project_name": "my-project"}}
    assert config.checkout is None
    assert config.skip == []


def test_load_with_checkout_and_skip(tmp_path):
    cruft_data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {}},
        "checkout": "main",
        "skip": ["go.sum", "*.lock"],
    }
    (tmp_path / ".cruft.json").write_text(json.dumps(cruft_data))

    config = CruftConfig.load(tmp_path)

    assert config.checkout == "main"
    assert config.skip == ["go.sum", "*.lock"]


def test_load_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        CruftConfig.load(tmp_path)


def test_save_and_reload(tmp_path):
    config = CruftConfig(
        template="https://github.com/owner/template",
        commit="def456",
        context={"cookiecutter": {"project_name": "my-project", "author": "Jane"}},
        checkout="main",
        skip=["go.sum"],
    )
    config.save(tmp_path)

    loaded = CruftConfig.load(tmp_path)
    assert loaded.template == config.template
    assert loaded.commit == config.commit
    assert loaded.context == config.context
    assert loaded.checkout == config.checkout
    assert loaded.skip == config.skip


def test_save_omits_none_checkout(tmp_path):
    config = CruftConfig(
        template="https://github.com/owner/template",
        commit="abc123",
        context={"cookiecutter": {}},
    )
    config.save(tmp_path)

    raw = json.loads((tmp_path / ".cruft.json").read_text())
    assert "checkout" not in raw
    assert "skip" not in raw
