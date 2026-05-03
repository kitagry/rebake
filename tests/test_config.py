import json

import pytest
import yaml

from rebake.config import CruftConfig


def test_load_basic_from_rebake_yaml(tmp_path):
    data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {"project_name": "my-project"}},
    }
    (tmp_path / "rebake.yaml").write_text(yaml.dump(data, allow_unicode=True))

    config = CruftConfig.load(tmp_path)

    assert config.template == "https://github.com/owner/template"
    assert config.commit == "abc123"
    assert config.context == {"cookiecutter": {"project_name": "my-project"}}
    assert config.checkout is None
    assert config.skip == []


def test_load_with_checkout_and_skip_from_rebake_yaml(tmp_path):
    data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {}},
        "checkout": "main",
        "skip": ["go.sum", "*.lock"],
    }
    (tmp_path / "rebake.yaml").write_text(yaml.dump(data, allow_unicode=True))

    config = CruftConfig.load(tmp_path)

    assert config.checkout == "main"
    assert config.skip == ["go.sum", "*.lock"]


def test_load_falls_back_to_cruft_json(tmp_path):
    cruft_data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {"project_name": "my-project"}},
    }
    (tmp_path / ".cruft.json").write_text(json.dumps(cruft_data))

    config = CruftConfig.load(tmp_path)

    assert config.template == "https://github.com/owner/template"
    assert config.commit == "abc123"


def test_load_prefers_rebake_yaml_over_cruft_json(tmp_path):
    (tmp_path / "rebake.yaml").write_text(
        yaml.dump({"template": "https://github.com/owner/rebake-template", "commit": "new111", "context": {}})
    )
    (tmp_path / ".cruft.json").write_text(
        json.dumps({"template": "https://github.com/owner/cruft-template", "commit": "old999", "context": {}})
    )

    config = CruftConfig.load(tmp_path)

    assert config.commit == "new111"


def test_load_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        CruftConfig.load(tmp_path)


def test_save_writes_rebake_yaml(tmp_path):
    config = CruftConfig(
        template="https://github.com/owner/template",
        commit="def456",
        context={"cookiecutter": {"project_name": "my-project", "author": "Jane"}},
        checkout="main",
        skip=["go.sum"],
    )
    config.save(tmp_path)

    assert (tmp_path / "rebake.yaml").exists()


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

    raw = yaml.safe_load((tmp_path / "rebake.yaml").read_text())
    assert "checkout" not in raw
    assert "skip" not in raw


def test_save_deletes_cruft_json_if_exists(tmp_path):
    cruft_json = tmp_path / ".cruft.json"
    cruft_json.write_text(json.dumps({"template": "x", "commit": "y", "context": {}}))

    config = CruftConfig(
        template="https://github.com/owner/template",
        commit="abc123",
        context={"cookiecutter": {}},
    )
    config.save(tmp_path)

    assert not cruft_json.exists()


def test_save_japanese_text_not_escaped(tmp_path):
    config = CruftConfig(
        template="https://github.com/owner/template",
        commit="abc123",
        context={"cookiecutter": {"project_name": "テストプロジェクト"}},
    )
    config.save(tmp_path)

    raw_text = (tmp_path / "rebake.yaml").read_text()
    assert "テストプロジェクト" in raw_text
    assert "\\u" not in raw_text
