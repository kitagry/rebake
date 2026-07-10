import json

import pytest
import yaml

from rebake.config import CruftConfig, RebakeConfig


def _first(tmp_path):
    """Load the sole template link (single-template helper for tests)."""
    return RebakeConfig.load(tmp_path).templates[0]


def test_load_basic_from_rebake_yaml(tmp_path):
    data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {"project_name": "my-project"}},
    }
    (tmp_path / "rebake.yaml").write_text(yaml.dump(data, allow_unicode=True))

    entry = _first(tmp_path)

    assert entry.template == "https://github.com/owner/template"
    assert entry.commit == "abc123"
    assert entry.context == {"cookiecutter": {"project_name": "my-project"}}
    assert entry.checkout is None
    assert entry.skip == []


def test_load_with_checkout_and_skip_from_rebake_yaml(tmp_path):
    data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {}},
        "checkout": "main",
        "skip": ["go.sum", "*.lock"],
    }
    (tmp_path / "rebake.yaml").write_text(yaml.dump(data, allow_unicode=True))

    entry = _first(tmp_path)

    assert entry.checkout == "main"
    assert entry.skip == ["go.sum", "*.lock"]


def test_load_falls_back_to_cruft_json(tmp_path):
    cruft_data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {"project_name": "my-project"}},
    }
    (tmp_path / ".cruft.json").write_text(json.dumps(cruft_data))

    entry = _first(tmp_path)

    assert entry.template == "https://github.com/owner/template"
    assert entry.commit == "abc123"


def test_load_prefers_rebake_yaml_over_cruft_json(tmp_path):
    (tmp_path / "rebake.yaml").write_text(
        yaml.dump({"template": "https://github.com/owner/rebake-template", "commit": "new111", "context": {}})
    )
    (tmp_path / ".cruft.json").write_text(
        json.dumps({"template": "https://github.com/owner/cruft-template", "commit": "old999", "context": {}})
    )

    assert _first(tmp_path).commit == "new111"


def test_load_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        RebakeConfig.load(tmp_path)


def test_save_writes_rebake_yaml(tmp_path):
    config = RebakeConfig(
        templates=[
            CruftConfig(
                template="https://github.com/owner/template",
                commit="def456",
                context={"cookiecutter": {"project_name": "my-project", "author": "Jane"}},
                checkout="main",
                skip=["go.sum"],
            )
        ]
    )
    config.save(tmp_path)

    assert (tmp_path / "rebake.yaml").exists()


def test_save_and_reload(tmp_path):
    entry = CruftConfig(
        template="https://github.com/owner/template",
        commit="def456",
        context={"cookiecutter": {"project_name": "my-project", "author": "Jane"}},
        checkout="main",
        skip=["go.sum"],
    )
    RebakeConfig(templates=[entry]).save(tmp_path)

    loaded = _first(tmp_path)
    assert loaded.template == entry.template
    assert loaded.commit == entry.commit
    assert loaded.context == entry.context
    assert loaded.checkout == entry.checkout
    assert loaded.skip == entry.skip


def test_save_omits_none_checkout(tmp_path):
    RebakeConfig(
        templates=[
            CruftConfig(template="https://github.com/owner/template", commit="abc123", context={"cookiecutter": {}})
        ]
    ).save(tmp_path)

    raw = yaml.safe_load((tmp_path / "rebake.yaml").read_text())["templates"][0]
    assert "checkout" not in raw
    assert "skip" not in raw


def test_save_deletes_cruft_json_if_exists(tmp_path):
    cruft_json = tmp_path / ".cruft.json"
    cruft_json.write_text(json.dumps({"template": "x", "commit": "y", "context": {}}))

    RebakeConfig(
        templates=[
            CruftConfig(template="https://github.com/owner/template", commit="abc123", context={"cookiecutter": {}})
        ]
    ).save(tmp_path)

    assert not cruft_json.exists()


def test_save_japanese_text_not_escaped(tmp_path):
    RebakeConfig(
        templates=[
            CruftConfig(
                template="https://github.com/owner/template",
                commit="abc123",
                context={"cookiecutter": {"project_name": "テストプロジェクト"}},
            )
        ]
    ).save(tmp_path)

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

    assert _first(tmp_path).hooks == {
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

    assert _first(tmp_path).hooks == {}


def test_save_and_reload_with_hooks(tmp_path):
    RebakeConfig(
        templates=[
            CruftConfig(
                template="https://github.com/owner/template",
                commit="abc123",
                context={"cookiecutter": {}},
                hooks={"post-update": ["go generate ./..."]},
            )
        ]
    ).save(tmp_path)

    assert _first(tmp_path).hooks == {"post-update": ["go generate ./..."]}


def test_save_omits_empty_hooks(tmp_path):
    RebakeConfig(
        templates=[
            CruftConfig(template="https://github.com/owner/template", commit="abc123", context={"cookiecutter": {}})
        ]
    ).save(tmp_path)

    raw = yaml.safe_load((tmp_path / "rebake.yaml").read_text())["templates"][0]
    assert "hooks" not in raw


def test_rebake_config_load_multi_form(tmp_path):
    data = {
        "templates": [
            {"template": "https://github.com/owner/common", "commit": "aaa", "context": {"cookiecutter": {}}},
            {
                "template": "https://github.com/owner/batch",
                "commit": "bbb",
                "context": {"cookiecutter": {}},
                "target_directory": "batch",
            },
        ]
    }
    (tmp_path / "rebake.yaml").write_text(yaml.dump(data, allow_unicode=True))

    config = RebakeConfig.load(tmp_path)

    assert len(config.templates) == 2
    assert config.templates[0].template == "https://github.com/owner/common"
    assert config.templates[0].target_directory == "."
    assert config.templates[1].template == "https://github.com/owner/batch"
    assert config.templates[1].target_directory == "batch"


def test_rebake_config_load_wraps_legacy_single_rebake_yaml(tmp_path):
    data = {"template": "https://github.com/owner/template", "commit": "abc123", "context": {"cookiecutter": {}}}
    (tmp_path / "rebake.yaml").write_text(yaml.dump(data, allow_unicode=True))

    config = RebakeConfig.load(tmp_path)

    assert len(config.templates) == 1
    assert config.templates[0].template == "https://github.com/owner/template"
    assert config.templates[0].target_directory == "."


def test_rebake_config_load_wraps_legacy_cruft_json(tmp_path):
    data = {"template": "https://github.com/owner/template", "commit": "abc123", "context": {"cookiecutter": {}}}
    (tmp_path / ".cruft.json").write_text(json.dumps(data))

    config = RebakeConfig.load(tmp_path)

    assert len(config.templates) == 1
    assert config.templates[0].target_directory == "."


def test_cruft_json_directory_key_is_ignored(tmp_path):
    # cruft's `directory` means a sub-directory INSIDE the template repo, the
    # opposite of rebake's output-side `target_directory`. It must be ignored,
    # otherwise patches would be applied to the wrong place.
    data = {
        "template": "https://github.com/owner/template",
        "commit": "abc123",
        "context": {"cookiecutter": {}},
        "directory": "some-template-subdir",
    }
    (tmp_path / ".cruft.json").write_text(json.dumps(data))

    entry = RebakeConfig.load(tmp_path).templates[0]

    assert entry.target_directory == "."
    assert tmp_path / entry.target_directory == tmp_path


def test_rebake_config_load_unrecognized_schema_raises(tmp_path):
    (tmp_path / "rebake.yaml").write_text(yaml.dump({"unexpected": "shape"}))

    with pytest.raises(ValueError):
        RebakeConfig.load(tmp_path)


def test_rebake_config_load_empty_templates_raises(tmp_path):
    # Symmetric with save(): an empty list must not silently read as up-to-date.
    (tmp_path / "rebake.yaml").write_text(yaml.dump({"templates": []}))

    with pytest.raises(ValueError):
        RebakeConfig.load(tmp_path)


def test_rebake_config_save_single_entry_uses_templates_list(tmp_path):
    RebakeConfig(
        templates=[
            CruftConfig(template="https://github.com/owner/template", commit="abc123", context={"cookiecutter": {}})
        ]
    ).save(tmp_path)

    raw = yaml.safe_load((tmp_path / "rebake.yaml").read_text())
    assert [entry["template"] for entry in raw["templates"]] == ["https://github.com/owner/template"]


def test_rebake_config_save_multi_entry_uses_templates_list(tmp_path):
    config = RebakeConfig(
        templates=[
            CruftConfig(template="https://github.com/owner/common", commit="aaa", context={"cookiecutter": {}}),
            CruftConfig(
                template="https://github.com/owner/batch",
                commit="bbb",
                context={"cookiecutter": {}},
                target_directory="batch",
            ),
        ]
    )
    config.save(tmp_path)

    raw = yaml.safe_load((tmp_path / "rebake.yaml").read_text())
    assert [entry["template"] for entry in raw["templates"]] == [
        "https://github.com/owner/common",
        "https://github.com/owner/batch",
    ]
    # target_directory "." is omitted, non-default is kept
    assert "target_directory" not in raw["templates"][0]
    assert raw["templates"][1]["target_directory"] == "batch"


def test_rebake_config_save_and_reload_multi(tmp_path):
    config = RebakeConfig(
        templates=[
            CruftConfig(template="https://github.com/owner/common", commit="aaa", context={"cookiecutter": {}}),
            CruftConfig(
                template="https://github.com/owner/batch",
                commit="bbb",
                context={"cookiecutter": {"project_name": "x"}},
                checkout="main",
                target_directory="batch",
                hooks={"post-update": ["make fmt"]},
            ),
        ]
    )
    config.save(tmp_path)

    loaded = RebakeConfig.load(tmp_path)
    assert len(loaded.templates) == 2
    assert loaded.templates[1].checkout == "main"
    assert loaded.templates[1].target_directory == "batch"
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
