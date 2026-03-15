from __future__ import annotations

import os
import platform
import stat
import sys
import textwrap
from pathlib import Path

import pytest


def _is_windows() -> bool:
    return platform.system().lower() == "windows"


@pytest.fixture
def fake_venv(tmp_path):
    """Create a minimal venv structure with a real python symlink/copy."""
    venv_dir = tmp_path / ".venv"
    if _is_windows():
        bin_dir = venv_dir / "Scripts"
        python_name = "python.exe"
    else:
        bin_dir = venv_dir / "bin"
        python_name = "python"

    bin_dir.mkdir(parents=True)
    python_path = bin_dir / python_name

    real_python = Path(sys.executable).resolve()
    cfg = venv_dir / "pyvenv.cfg"
    cfg.write_text(
        f"home = {real_python.parent}\n"
        f"include-system-site-packages = false\n"
    )

    try:
        python_path.symlink_to(real_python)
    except OSError:
        # windows without symlink privilege -- just copy
        import shutil
        shutil.copy2(real_python, python_path)

    return venv_dir


@pytest.fixture
def simple_script(tmp_path):
    """A standalone script that prints to stdout and stderr."""
    script = tmp_path / "hello.py"
    script.write_text(textwrap.dedent("""\
        import sys
        print("STDOUT_HELLO")
        print("STDERR_HELLO", file=sys.stderr)
    """))
    return script


@pytest.fixture
def script_with_sibling_import(tmp_path):
    """A script that imports from a sibling module in the same directory."""
    project = tmp_path / "myproject"
    project.mkdir()

    (project / "helpers.py").write_text("VALUE = 42\n")
    main = project / "main.py"
    main.write_text(textwrap.dedent("""\
        from helpers import VALUE
        print(f"SIBLING_IMPORT_OK={VALUE}")
    """))
    return main


@pytest.fixture
def script_in_package(tmp_path):
    """A script inside a python package (has __init__.py up the tree)."""
    pkg = tmp_path / "mypkg" / "sub"
    pkg.mkdir(parents=True)

    (tmp_path / "mypkg" / "__init__.py").write_text("")
    (tmp_path / "mypkg" / "sub" / "__init__.py").write_text("")
    (tmp_path / "mypkg" / "shared.py").write_text("SHARED = 'from_parent'\n")

    runner = pkg / "run.py"
    runner.write_text(textwrap.dedent("""\
        import sys, os
        print(f"PKG_CWD={os.getcwd()}")
        print(f"PKG_SYSPATH0={sys.path[0]}")
        from mypkg.shared import SHARED
        print(f"PKG_IMPORT_OK={SHARED}")
    """))
    return runner


@pytest.fixture
def shell_script(tmp_path):
    """A non-python executable script."""
    if _is_windows():
        script = tmp_path / "run.bat"
        script.write_text("@echo off\necho SHELL_OK\n")
    else:
        script = tmp_path / "run.sh"
        script.write_text("#!/bin/sh\necho SHELL_OK\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


@pytest.fixture
def script_that_checks_venv(tmp_path):
    """A script that reports whether it sees VIRTUAL_ENV."""
    script = tmp_path / "check_venv.py"
    script.write_text(textwrap.dedent("""\
        import os, sys
        venv = os.environ.get("VIRTUAL_ENV", "")
        print(f"VIRTUAL_ENV={venv}")
        print(f"SYS_EXEC={sys.executable}")
    """))
    return script


@pytest.fixture
def script_with_logging(tmp_path):
    """A script that emits log lines via the bootstrap logger."""
    script = tmp_path / "log_test.py"
    script.write_text(textwrap.dedent("""\
        import logging
        logger = logging.getLogger("child_logger")
        logger.info("CHILD_LOG_INFO")
        logger.warning("CHILD_LOG_WARN")
        print("CHILD_PRINT")
    """))
    return script


@pytest.fixture
def script_with_exit_code(tmp_path):
    """A script that exits with a specific code."""
    script = tmp_path / "exits.py"
    script.write_text("import sys; sys.exit(7)\n")
    return script