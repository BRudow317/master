"""Child process environment preparation for master.py"""

from __future__ import annotations

import logging
import os
import platform
import sys
from pathlib import Path

_PROGRAM_NAME: str = os.getenv("PROGRAM_NAME", "default")
_BACKUP_LIB: str | None = os.getenv("BACKUP_LIB", None)

logger = logging.getLogger(__name__)

_BOOTSTRAP = (
    "import logging,os,sys;"
    "logging.basicConfig("
    "level=getattr(logging,os.environ.get('LOG_LEVEL','WARNING').upper(),logging.WARNING),"
    "stream=sys.stdout,"
    "format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',"
    "force=True)"
)

_PYTHON_BASENAMES = frozenset({
    "python", "python3", "python.exe",
    "python3.exe", "py", "py.exe", "pythonw.exe",
})

_SCRIPT_EXTENSIONS = frozenset({
    ".py", ".sh", ".js", ".jar", ".rb", ".pl", ".ts",
})

def _is_windows() -> bool:
    return platform.system().lower() == "windows"

def venv_paths(venv_dir: str | Path) -> tuple[Path, Path]:
    venv = Path(venv_dir)
    if _is_windows():
        return venv / "Scripts" / "python.exe", venv / "Scripts"
    return venv / "bin" / "python", venv / "bin"

def validate_venv(venv_dir: str | Path) -> tuple[Path, Path]:
    python_path, bin_dir = venv_paths(venv_dir)
    if not python_path.is_file():
        raise FileNotFoundError(
            f"{_PROGRAM_NAME}: venv python not found at {python_path}"
        )
    return python_path, bin_dir

def _find_backup_library(name: str | None = _BACKUP_LIB) -> Path | None:
    if name is None:
        return None
    anchor = Path(__file__).resolve().parent
    for base in (anchor, anchor.parent):
        candidate = base / name
        if candidate.is_dir():
            found = str(candidate)
            if found not in sys.path:
                import site
                sys.path.insert(0, found)
                site.addsitedir(found)
            return candidate
    logger.debug("Backup library not found: %s", name)
    return None

def reexec_into_venv_if_needed(args) -> None:
    if not getattr(args, "venv", ""):
        return
    if getattr(args, "venv_mode", "").lower() not in ("master", _PROGRAM_NAME):
        return

    venv_python, _ = validate_venv(args.venv)
    if os.path.abspath(sys.executable) == os.path.abspath(venv_python):
        return

    tripwire = f"_{_PROGRAM_NAME}_REEXECED".upper()
    if os.environ.get(tripwire) == "1":
        raise RuntimeError(
            f"Fatal: {_PROGRAM_NAME} re-exec loop detected ({tripwire}=1)"
        )

    logger.debug("Re-executing under venv interpreter: %s", venv_python)
    new_env = os.environ.copy()
    _apply_venv_to_env(new_env, args.venv)
    new_env[tripwire] = "1"
    os.execve(
        str(venv_python), 
        [str(venv_python)] + sys.argv,
        new_env
    )

def prepare_child(
    args,
    config_vars: dict[str, str] | None = None,
) -> tuple[list[str], dict[str, str], str]:
    """Build (cmd, env, cwd) for subprocess.Popen"""
    config_vars = config_vars or {}

    python = _resolve_python(venv=getattr(args, "venv", ""))
    script_dir = _derive_script_dir(args.exec)
    pkg_root = _derive_package_root(args.exec)

    env = _build_env(
        config_vars=config_vars,
        venv=getattr(args, "venv", ""),
        verbose=getattr(args, "verbose", False),
    )

    paths_to_add = []
    if pkg_root:
        paths_to_add.append(pkg_root)
    if script_dir and script_dir != pkg_root:
        paths_to_add.append(script_dir)

    existing = env.get("PYTHONPATH", "")
    existing_parts = existing.split(os.pathsep) if existing else []
    for p in paths_to_add:
        if p not in existing_parts:
            existing_parts.insert(0, p)
    env["PYTHONPATH"] = os.pathsep.join(existing_parts)

    cmd = _build_cmd(raw_cmd=args.exec, python=python, script_dir=script_dir)
    cwd = script_dir or os.getcwd()

    return cmd, env, cwd


# -- private helpers --

def _resolve_python(venv: str) -> str:
    if venv:
        python_path, _ = venv_paths(venv)
        if python_path.exists():
            return str(python_path)

    backup = _find_backup_library()
    if backup is not None:
        python_path, _ = venv_paths(backup)
        if python_path.exists():
            return str(python_path)

    return sys.executable


def _apply_venv_to_env(env: dict[str, str], venv_dir: str | Path) -> None:
    python_path, bin_dir = venv_paths(venv_dir)
    if python_path.exists():
        env["VIRTUAL_ENV"] = str(venv_dir)
        env.pop("PYTHONHOME", None)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    else:
        existing = env.get("PYTHONPATH", "")
        target = str(venv_dir)
        env["PYTHONPATH"] = (
            f"{existing}{os.pathsep}{target}" if existing else target
        )


def _build_env(
    *,
    config_vars: dict[str, str],
    venv: str,
    verbose: bool,
) -> dict[str, str]:
    env = os.environ.copy()
    env.update(config_vars)
    env.setdefault("LOG_LEVEL", "DEBUG" if verbose else "INFO")
    if venv:
        _apply_venv_to_env(env, venv)
    return env


def _find_target_file(raw_cmd: list[str]) -> Path | None:
    """Find the first token that looks like an existing file to execute."""
    for token in raw_cmd:
        p = Path(token)
        if p.is_file() and p.suffix in _SCRIPT_EXTENSIONS:
            return p.resolve()
        if p.is_file():
            return p.resolve()
    return None


def _derive_script_dir(raw_cmd: list[str]) -> str:
    """Parent directory of the target file -- used as child cwd."""
    target = _find_target_file(raw_cmd)
    if target is not None:
        return str(target.parent)
    return os.getcwd()


def _derive_package_root(raw_cmd: list[str]) -> str:
    """Walk up from the script until we leave a Python package.
    Used for PYTHONPATH so deep-package imports resolve."""
    target = _find_target_file(raw_cmd)
    if target is None:
        return os.getcwd()
    if target.suffix != ".py":
        return str(target.parent)

    root = target.parent
    while (root / "__init__.py").exists() and root != root.parent:
        root = root.parent
    return str(root)


def _resolve_tokens(raw_cmd: list[str]) -> list[str]:
    return [
        str(Path(token).resolve()) if Path(token).is_file() else token
        for token in raw_cmd
    ]


def _build_cmd(*, raw_cmd: list[str], python: str, script_dir: str) -> list[str]:
    cmd = _resolve_tokens(raw_cmd)
    base = os.path.basename(cmd[0]).lower()

    if base in _PYTHON_BASENAMES:
        cmd[0] = python
    elif cmd[0].lower().endswith(".py") and os.path.isfile(cmd[0]):
        cmd = [python] + cmd

    if cmd[0] != python:
        return cmd

    return _inject_bootstrap(cmd, python, script_dir)


def _inject_bootstrap(cmd: list[str], python: str, script_dir: str) -> list[str]:
    rest = cmd[1:]
    path_fix = f"import sys; sys.path.insert(0, {script_dir!r});"

    if len(rest) >= 2 and rest[0] == "-m":
        module = rest[1]
        extra = rest[2:]
        return [
            python, "-c",
            f"{path_fix}"
            f"{_BOOTSTRAP};"
            f"import runpy;"
            f"sys.argv=[{module!r}]+{extra!r};"
            f"runpy.run_module({module!r},run_name='__main__',alter_sys=True)",
        ]

    if rest and rest[0].endswith(".py") and os.path.isfile(rest[0]):
        script = rest[0].replace("\\", "/")
        extra = rest[1:]
        return [
            python, "-c",
            f"{path_fix}"
            f"{_BOOTSTRAP};"
            f"import runpy;"
            f"sys.argv=[{script!r}]+{extra!r};"
            f"runpy.run_path({script!r},run_name='__main__')",
        ]

    return cmd