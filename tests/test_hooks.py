import pytest

from rebake.hooks import run_hooks


def test_run_hooks_executes_commands(tmp_path):
    sentinel = tmp_path / "ran"
    commands = [f"touch {sentinel}"]
    run_hooks("post-update", tmp_path, commands=commands)

    assert sentinel.exists()


def test_run_hooks_raises_on_failure(tmp_path):
    commands = ["exit 1"]
    with pytest.raises(RuntimeError, match="post-update"):
        run_hooks("post-update", tmp_path, commands=commands)


def test_run_hooks_raises_with_failing_command_in_message(tmp_path):
    commands = ["exit 42"]
    with pytest.raises(RuntimeError, match="exit 42"):
        run_hooks("post-update", tmp_path, commands=commands)


def test_run_hooks_passes_env_vars(tmp_path):
    out = tmp_path / "env_out"
    commands = [f"echo $REBAKE_TEMPLATE > {out}"]
    run_hooks("post-update", tmp_path, commands=commands, env={"REBAKE_TEMPLATE": "https://example.com/tmpl"})

    assert "https://example.com/tmpl" in out.read_text()


def test_run_hooks_runs_in_project_dir(tmp_path):
    out = tmp_path / "cwd_out"
    commands = [f"pwd > {out}"]
    run_hooks("post-update", tmp_path, commands=commands)

    assert str(tmp_path) in out.read_text()


def test_run_hooks_noop_when_no_commands(tmp_path):
    # should not raise
    run_hooks("post-update", tmp_path, commands=[])


def test_run_hooks_runs_multiple_commands_in_order(tmp_path):
    out = tmp_path / "order"
    commands = [f"echo first > {out}", f"echo second >> {out}"]
    run_hooks("post-update", tmp_path, commands=commands)

    lines = out.read_text().splitlines()
    assert lines[0] == "first"
    assert lines[1] == "second"


def test_run_hooks_stops_on_first_failure(tmp_path):
    sentinel = tmp_path / "should_not_exist"
    commands = ["exit 1", f"touch {sentinel}"]
    with pytest.raises(RuntimeError):
        run_hooks("post-update", tmp_path, commands=commands)

    assert not sentinel.exists()
