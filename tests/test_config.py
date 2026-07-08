import json

import pytest
import yaml

from rebake.config import CruftConfig, RebakeConfig


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


def test_load_with_hooks_from_rebake_yaml(tmp_path):
    data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {}},
        "hooks": {
            "pre-update": ["make lint"],
            "post-update": ["make fmt", "make test"],
        },
    }
    (tmp_path / "rebake.yaml").write_text(yaml.dump(data, allow_unicode=True))

    config = CruftConfig.load(tmp_path)

    assert config.hooks == {
        "pre-update": ["make lint"],
        "post-update": ["make fmt", "make test"],
    }


def test_load_hooks_defaults_to_empty(tmp_path):
    data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {}},
    }
    (tmp_path / "rebake.yaml").write_text(yaml.dump(data, allow_unicode=True))

    config = CruftConfig.load(tmp_path)

    assert config.hooks == {}


def test_save_and_reload_with_hooks(tmp_path):
    config = CruftConfig(
        template="https://github.com/owner/template",
        commit="abc123",
        context={"cookiecutter": {}},
        hooks={"post-update": ["go generate ./..."]},
    )
    config.save(tmp_path)

    loaded = CruftConfig.load(tmp_path)
    assert loaded.hooks == {"post-update": ["go generate ./..."]}


def test_save_omits_empty_hooks(tmp_path):
    config = CruftConfig(
        template="https://github.com/owner/template",
        commit="abc123",
        context={"cookiecutter": {}},
    )
    config.save(tmp_path)

    raw = yaml.safe_load((tmp_path / "rebake.yaml").read_text())
    assert "hooks" not in raw


def test_rebake_config_load_multi_form(tmp_path):
    data = {
        "templates": [
            {"template": "https://github.com/owner/common", "commit": "aaa", "context": {"cookiecutter": {}}},
            {
                "template": "https://github.com/owner/batch",
                "commit": "bbb",
                "context": {"cookiecutter": {}},
                "directory": "batch",
            },
        ]
    }
    (tmp_path / "rebake.yaml").write_text(yaml.dump(data, allow_unicode=True))

    config = RebakeConfig.load(tmp_path)

    assert len(config.templates) == 2
    assert config.templates[0].template == "https://github.com/owner/common"
    assert config.templates[0].directory == "."
    assert config.templates[1].template == "https://github.com/owner/batch"
    assert config.templates[1].directory == "batch"


def test_rebake_config_load_wraps_legacy_single_rebake_yaml(tmp_path):
    data = {"template": "https://github.com/owner/template", "commit": "abc123", "context": {"cookiecutter": {}}}
    (tmp_path / "rebake.yaml").write_text(yaml.dump(data, allow_unicode=True))

    config = RebakeConfig.load(tmp_path)

    assert len(config.templates) == 1
    assert config.templates[0].template == "https://github.com/owner/template"
    assert config.templates[0].directory == "."


def test_rebake_config_load_wraps_legacy_cruft_json(tmp_path):
    data = {"template": "https://github.com/owner/template", "commit": "abc123", "context": {"cookiecutter": {}}}
    (tmp_path / ".cruft.json").write_text(json.dumps(data))

    config = RebakeConfig.load(tmp_path)

    assert len(config.templates) == 1
    assert config.templates[0].directory == "."


def test_rebake_config_load_cruft_json_null_directory_normalized_to_root(tmp_path):
    # cruft writes its own (unrelated) `directory` key, commonly as null.
    data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {}},
        "directory": None,
        "skip": [],
    }
    (tmp_path / ".cruft.json").write_text(json.dumps(data))

    entry = RebakeConfig.load(tmp_path).templates[0]

    assert entry.directory == "."
    # must be a valid path component (regression: `project_dir / None` raised TypeError)
    assert tmp_path / entry.directory == tmp_path


def test_rebake_config_load_unrecognized_schema_raises(tmp_path):
    (tmp_path / "rebake.yaml").write_text(yaml.dump({"unexpected": "shape"}))

    with pytest.raises(ValueError):
        RebakeConfig.load(tmp_path)


def test_rebake_config_save_single_entry_uses_legacy_top_level_form(tmp_path):
    config = RebakeConfig(
        templates=[
            CruftConfig(template="https://github.com/owner/template", commit="abc123", context={"cookiecutter": {}})
        ]
    )
    config.save(tmp_path)

    raw = yaml.safe_load((tmp_path / "rebake.yaml").read_text())
    assert "templates" not in raw
    assert raw["template"] == "https://github.com/owner/template"


def test_rebake_config_save_multi_entry_uses_templates_list(tmp_path):
    config = RebakeConfig(
        templates=[
            CruftConfig(template="https://github.com/owner/common", commit="aaa", context={"cookiecutter": {}}),
            CruftConfig(
                template="https://github.com/owner/batch",
                commit="bbb",
                context={"cookiecutter": {}},
                directory="batch",
            ),
        ]
    )
    config.save(tmp_path)

    raw = yaml.safe_load((tmp_path / "rebake.yaml").read_text())
    assert [entry["template"] for entry in raw["templates"]] == [
        "https://github.com/owner/common",
        "https://github.com/owner/batch",
    ]
    # directory "." is omitted, non-default is kept
    assert "directory" not in raw["templates"][0]
    assert raw["templates"][1]["directory"] == "batch"


def test_rebake_config_save_and_reload_multi(tmp_path):
    config = RebakeConfig(
        templates=[
            CruftConfig(template="https://github.com/owner/common", commit="aaa", context={"cookiecutter": {}}),
            CruftConfig(
                template="https://github.com/owner/batch",
                commit="bbb",
                context={"cookiecutter": {"project_name": "x"}},
                checkout="main",
                directory="batch",
                hooks={"post-update": ["make fmt"]},
            ),
        ]
    )
    config.save(tmp_path)

    loaded = RebakeConfig.load(tmp_path)
    assert len(loaded.templates) == 2
    assert loaded.templates[1].checkout == "main"
    assert loaded.templates[1].directory == "batch"
    assert loaded.templates[1].hooks == {"post-update": ["make fmt"]}


def test_rebake_config_save_multi_deletes_cruft_json(tmp_path):
    (tmp_path / ".cruft.json").write_text(json.dumps({"template": "x", "commit": "y", "context": {}}))
    config = RebakeConfig(
        templates=[
            CruftConfig(template="https://github.com/owner/common", commit="aaa", context={"cookiecutter": {}}),
            CruftConfig(template="https://github.com/owner/batch", commit="bbb", context={"cookiecutter": {}}),
        ]
    )
    config.save(tmp_path)

    assert not (tmp_path / ".cruft.json").exists()


def test_rebake_config_save_empty_raises(tmp_path):
    config = RebakeConfig(templates=[])
    with pytest.raises(ValueError):
        config.save(tmp_path)


def test_cruft_config_load_returns_first_entry_of_multi(tmp_path):
    data = {
        "templates": [
            {"template": "https://github.com/owner/common", "commit": "aaa", "context": {"cookiecutter": {}}},
            {"template": "https://github.com/owner/batch", "commit": "bbb", "context": {"cookiecutter": {}}},
        ]
    }
    (tmp_path / "rebake.yaml").write_text(yaml.dump(data, allow_unicode=True))

    config = CruftConfig.load(tmp_path)

    assert config.template == "https://github.com/owner/common"
