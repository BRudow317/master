from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

import pytest

from master_utils.child_env_setup import (
    prepare_child,
    venv_paths,
    validate_venv,
    _derive_script_dir,
    _derive_package_root,
    _find_target_file,
    _build_cmd,
    _inject_bootstrap,
    _apply_venv_to_env,
    _build_env,
    _resolve_tokens,
)


def make_namespace(**kwargs):
    import argparse
    ns = argparse.Namespace()
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


def _is_windows():
    return platform.system().lower() == "windows"


# -- venv_paths / validate_venv --

class TestVenvPaths:
    def test_linux_layout(self, monkeypatch, tmp_path):
        monkeypatch.setattr("master_utils.child_env_setup._is_windows", lambda: False)
        py, bdir = venv_paths(tmp_path / ".venv")
        assert py == tmp_path / ".venv" / "bin" / "python"
        assert bdir == tmp_path / ".venv" / "bin"

    def test_windows_layout(self, monkeypatch, tmp_path):
        monkeypatch.setattr("master_utils.child_env_setup._is_windows", lambda: True)
        py, bdir = venv_paths(tmp_path / ".venv")
        assert py == tmp_path / ".venv" / "Scripts" / "python.exe"
        assert bdir == tmp_path / ".venv" / "Scripts"

    def test_validate_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            validate_venv(tmp_path / "nonexistent")

    def test_validate_existing(self, fake_venv):
        py, bdir = validate_venv(fake_venv)
        assert py.is_file()


# -- _find_target_file --

class TestFindTargetFile:
    def test_finds_py(self, simple_script):
        result = _find_target_file(["python", str(simple_script)])
        assert result == simple_script.resolve()

    def test_finds_sh(self, shell_script):
        result = _find_target_file([str(shell_script)])
        assert result == shell_script.resolve()

    def test_skips_nonexistent(self):
        assert _find_target_file(["python", "no_such_file.py"]) is None

    def test_python_binary_skipped(self):
        result = _find_target_file(["python"])
        # "python" is not an existing .py file
        assert result is None


# -- _derive_script_dir / _derive_package_root --

class TestDeriveScriptDir:
    def test_returns_parent_of_script(self, simple_script):
        result = _derive_script_dir(["python", str(simple_script)])
        assert result == str(simple_script.resolve().parent)

    def test_falls_back_to_cwd(self):
        result = _derive_script_dir(["python", "nonexistent.py"])
        assert result == os.getcwd()


class TestDerivePackageRoot:
    def test_no_init_stays_at_parent(self, simple_script):
        result = _derive_package_root(["python", str(simple_script)])
        assert result == str(simple_script.resolve().parent)

    def test_walks_past_init(self, script_in_package):
        result = _derive_package_root(["python", str(script_in_package)])
        # should walk up past mypkg/sub/ and mypkg/ to tmp_path
        pkg_root = Path(result)
        assert not (pkg_root / "__init__.py").exists()
        assert pkg_root == script_in_package.resolve().parent.parent.parent

    def test_non_python_returns_parent(self, shell_script):
        result = _derive_package_root([str(shell_script)])
        assert result == str(shell_script.resolve().parent)


# -- _build_cmd --

class TestBuildCmd:
    def test_replaces_python_basename(self, simple_script):
        cmd = _build_cmd(
            raw_cmd=["python", str(simple_script)],
            python="/usr/bin/python3.11",
            script_dir=str(simple_script.parent),
        )
        assert cmd[0] == "/usr/bin/python3.11"

    def test_prepends_python_for_bare_py(self, simple_script):
        cmd = _build_cmd(
            raw_cmd=[str(simple_script)],
            python="/usr/bin/python3.11",
            script_dir=str(simple_script.parent),
        )
        assert cmd[0] == "/usr/bin/python3.11"

    def test_non_python_passthrough(self, shell_script):
        cmd = _build_cmd(
            raw_cmd=[str(shell_script)],
            python=sys.executable,
            script_dir=str(shell_script.parent),
        )
        # should not have injected python
        assert cmd[0] != sys.executable


# -- _inject_bootstrap --

class TestInjectBootstrap:
    def test_module_mode(self):
        cmd = _inject_bootstrap(
            [sys.executable, "-m", "http.server", "8080"],
            sys.executable,
            "/some/dir",
        )
        assert cmd[1] == "-c"
        code = cmd[2]
        assert "sys.path.insert(0, '/some/dir')" in code
        assert "run_module" in code
        assert "'http.server'" in code

    def test_script_mode(self, simple_script):
        cmd = _inject_bootstrap(
            [sys.executable, str(simple_script)],
            sys.executable,
            str(simple_script.parent),
        )
        assert cmd[1] == "-c"
        code = cmd[2]
        assert "sys.path.insert(0," in code
        assert "run_path" in code

    def test_unknown_passthrough(self):
        cmd = _inject_bootstrap(
            [sys.executable, "--version"],
            sys.executable,
            "/whatever",
        )
        assert cmd == [sys.executable, "--version"]


# -- _apply_venv_to_env --

class TestApplyVenvToEnv:
    def test_sets_virtual_env_and_path(self, fake_venv):
        env = {"PATH": "/usr/bin"}
        _apply_venv_to_env(env, fake_venv)
        assert env["VIRTUAL_ENV"] == str(fake_venv)
        assert "PYTHONHOME" not in env
        assert str(fake_venv) in env["PATH"]

    def test_removes_pythonhome(self, fake_venv):
        env = {"PATH": "/usr/bin", "PYTHONHOME": "/old"}
        _apply_venv_to_env(env, fake_venv)
        assert "PYTHONHOME" not in env

    def test_missing_venv_falls_back_to_pythonpath(self, tmp_path):
        bogus = tmp_path / "novenv"
        bogus.mkdir()
        env = {}
        _apply_venv_to_env(env, bogus)
        assert str(bogus) in env.get("PYTHONPATH", "")


# -- _build_env --

class TestBuildEnv:
    def test_config_vars_injected(self):
        env = _build_env(config_vars={"MY_KEY": "val"}, venv="", verbose=False)
        assert env["MY_KEY"] == "val"

    def test_verbose_sets_debug(self):
        env = _build_env(config_vars={}, venv="", verbose=True)
        assert env["LOG_LEVEL"] == "DEBUG"

    def test_default_log_level_info(self):
        env = _build_env(config_vars={}, venv="", verbose=False)
        assert env["LOG_LEVEL"] == "INFO"


# -- prepare_child (integration of all helpers) --

class TestPrepareChild:
    def test_basic_python_script(self, simple_script):
        args = make_namespace(
            exec=["python", str(simple_script)],
            venv="",
            verbose=False,
        )
        cmd, env, cwd = prepare_child(args)
        assert cmd[0] == sys.executable
        assert cwd == str(simple_script.resolve().parent)
        assert cwd in env["PYTHONPATH"]

    def test_venv_resolved_to_absolute(self, simple_script, fake_venv, monkeypatch):
        monkeypatch.chdir(fake_venv.parent)
        try:
            rel_venv = os.path.relpath(fake_venv)
        except ValueError:
            pytest.skip("cross-drive relpath not supported on Windows")
        args = make_namespace(
            exec=["python", str(simple_script)],
            venv=rel_venv,
            verbose=False,
        )
        cmd, env, cwd = prepare_child(args)
        assert os.path.isabs(env.get("VIRTUAL_ENV", "")), (
            f"VIRTUAL_ENV should be absolute, got {env.get('VIRTUAL_ENV', '')}"
        )

    def test_script_dir_and_pkg_root_both_on_pythonpath(self, script_in_package):
        args = make_namespace(
            exec=["python", str(script_in_package)],
            venv="",
            verbose=False,
        )
        cmd, env, cwd = prepare_child(args)
        pp = env["PYTHONPATH"]
        script_dir = str(script_in_package.resolve().parent)
        pkg_root = str(script_in_package.resolve().parent.parent.parent)
        assert script_dir in pp
        assert pkg_root in pp

    def test_config_vars_in_env(self, simple_script):
        args = make_namespace(
            exec=["python", str(simple_script)],
            venv="",
            verbose=False,
        )
        cmd, env, cwd = prepare_child(args, config_vars={"APP_ENV": "test"})
        assert env["APP_ENV"] == "test"

    def test_non_python_cwd(self, shell_script):
        args = make_namespace(
            exec=[str(shell_script)],
            venv="",
            verbose=False,
        )
        cmd, env, cwd = prepare_child(args)
        assert cwd == str(shell_script.resolve().parent)