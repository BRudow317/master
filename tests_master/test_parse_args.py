from __future__ import annotations

import pytest


def _parse(argv: list[str]):
    """Import locally so PROGRAM_NAME env var can be set per-test if needed."""
    from master_utils.parse_args import parse_args
    return parse_args(argv)


class TestExecParsing:
    def test_basic_exec(self):
        args, extra = _parse(["--exec", "python", "script.py"])
        assert args.exec == ["python", "script.py"]
        assert extra == []

    def test_exec_with_passthrough(self):
        args, extra = _parse(["--exec", "python", "script.py", "--", "--flag", "val"])
        assert args.exec == ["python", "script.py"]
        assert extra == ["--flag", "val"]

    def test_exec_with_cli_flags_after(self):
        args, _ = _parse(["--exec", "python", "script.py", "--venv", "/some/venv"])
        assert args.exec == ["python", "script.py"]
        assert args.venv == "/some/venv"

    def test_missing_exec_raises(self):
        with pytest.raises(SystemExit):
            _parse(["--venv", "/some/path"])


class TestOptionalFlags:
    def test_defaults(self):
        args, _ = _parse(["--exec", "python", "x.py"])
        assert args.env == ""
        assert args.config == ""
        assert args.venv == ""
        assert args.venv_mode == "child"
        assert args.verbose is False
        assert args.log_dir == "sys.stdout"

    def test_verbose_short(self):
        args, _ = _parse(["-v", "--exec", "python", "x.py"])
        assert args.verbose is True

    def test_venv_mode_master(self):
        args, _ = _parse(["--venv-mode", "master", "--exec", "python", "x.py"])
        assert args.venv_mode == "master"

    def test_env_flag(self):
        args, _ = _parse(["--env", "sit01", "--exec", "python", "x.py"])
        assert args.env == "sit01"

    def test_config_aliases(self):
        args, _ = _parse(["--config-file", "a.env", "--exec", "python", "x.py"])
        assert args.config == "a.env"

        args2, _ = _parse(["--config_file", "b.env", "--exec", "python", "x.py"])
        assert args2.config == "b.env"

    def test_log_dir(self):
        args, _ = _parse(["-l", "/tmp/logs", "--exec", "python", "x.py"])
        assert args.log_dir == "/tmp/logs"