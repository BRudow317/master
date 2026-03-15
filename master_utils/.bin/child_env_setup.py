from __future__ import annotations

import sys, platform, os
from pathlib import Path

_PROGRAM_NAME: str = os.getenv("PROGRAM_NAME", "quickbitlabs")
_BACKUP_LIB = os.getenv("BACKUP_LIB", None)

import logging
logger = logging.getLogger(__name__)

def get_venv_paths(venv_dir: str | Path) -> tuple[Path, Path]:
    venv = Path(venv_dir)
    if platform.system().lower() == "windows": python_path = venv / "Scripts" / "python.exe"; bin_dir = venv / "Scripts"
    else: python_path = venv / "bin" / "python"; bin_dir = venv / "bin"
    return python_path, bin_dir

def validate_venv(venv_dir: str | Path) -> tuple[Path, Path]:
    python_path, bin_dir = get_venv_paths(venv_dir)
    if not python_path.is_file(): raise FileNotFoundError(f"Error: {_PROGRAM_NAME}.validate_venv: Venv python not found: {python_path}")
    return python_path, bin_dir

def apply_env_to_child(child_env: dict[str, str], target_dir: str | Path) -> tuple[str, str]:
    python_path, bin_dir = get_venv_paths(target_dir)
    if python_path.exists():
        child_env["VIRTUAL_ENV"] = str(target_dir)
        child_env.pop("PYTHONHOME", None)
        child_env["PATH"] = f"{bin_dir}{os.pathsep}{child_env.get('PATH', '')}"
        return str(python_path), str(bin_dir)
    existing = child_env.get("PYTHONPATH", "")
    td = str(target_dir)
    child_env["PYTHONPATH"] = f"{existing}{os.pathsep}{td}" if existing else td
    return sys.executable, td

def backup_library(dir_name: str | None = _BACKUP_LIB) -> Path | None:
    if dir_name is None: return None
    
    def resolve_near(name: str, anchor: Path | None = None) -> Path | None:
        anchor = anchor or Path(__file__).resolve().parent
        for base in (anchor, anchor.parent):
            candidate = base / name
            if candidate.exists(): return candidate
        return None
    import site
    found = resolve_near(dir_name)
    if found is None:
        logger.debug(f"Backup library not found: {dir_name}")
        return None
    found_str = str(found)
    if found_str not in sys.path:
        sys.path.insert(0, found_str)
        site.addsitedir(found_str)
    return found

def reexec_into_venv_if_needed(args)->None:
    if args.venv == "": return

    if args.venv_mode.lower() not in ("master", _PROGRAM_NAME): return

    venv_python, _ = validate_venv(args.venv)
    current = os.path.abspath(sys.executable); target = os.path.abspath(venv_python)
    if current == target: return

    static_tripwire = str(f"_{_PROGRAM_NAME}_REEXECED").upper()
    if os.environ.get(static_tripwire) == "1": 
        raise RuntimeError(f"Fatal: {_PROGRAM_NAME}.reexec_into_venv_if_needed: {static_tripwire} == 1")
    
    logger.debug(f"{_PROGRAM_NAME}.reexec_into_venv_if_needed: Re-executing under venv interpreter: {venv_python}")
    new_env = os.environ.copy()
    apply_env_to_child(new_env, args.venv)
    new_env[static_tripwire] = "1"
    os.execve(venv_python, [str(venv_python)] + sys.argv, new_env)

def prepare_child(args, config_vars: dict[str, str]) -> tuple[list[str], dict[str, str], str]:
    child_env = os.environ.copy()
    child_env.update(config_vars)

    # Derive the project root from the exec command so master.py 
    
    cmd = [str(Path(tok).resolve()) if tok.endswith('.py') and Path(tok).exists() else tok for tok in args.exec]

    # Derive project root from the script path.
    script_path = next((Path(tok) for tok in cmd if tok.endswith('.py') and Path(tok).exists()), None)
    
    if script_path:
        parent = script_path.parent
        # Step up only if the script's directory is a package (has __init__.py) AND
        # the script itself is not named __main__.py or a clear entrypoint peer.
        script_root = str(parent.parent) if (parent / '__init__.py').exists() else str(parent)
    else:
        script_root = os.getcwd()
    existing_pythonpath = child_env.get('PYTHONPATH', '')
    child_env['PYTHONPATH'] = f"{script_root}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else script_root

    # Propagate verbosity to child process
    child_env.setdefault('LOG_LEVEL', 'DEBUG' if getattr(args, 'verbose', False) else 'INFO')

    if args.venv:
        venv_python, _ = apply_env_to_child(child_env, args.venv)
    else:
        fallback = backup_library()
        if fallback:
            venv_python, _ = apply_env_to_child(child_env, fallback)
        else:
            venv_python, _ = sys.executable, os.path.dirname(sys.executable)

    _BOOTSTRAP = (
        "import logging,os,sys;"
        "logging.basicConfig("
        "level=getattr(logging,os.environ.get('LOG_LEVEL','WARNING').upper(),logging.WARNING),"
        "stream=sys.stdout,"
        "format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',"
        "force=True)"
    )

    base = os.path.basename(cmd[0]).lower()
    python_like = {"python", "python3", "python.exe", "python3.exe", "py", "py.exe", "pythonw.exe"}
    if base in python_like:
        cmd[0] = venv_python
    elif cmd[0].lower().endswith('.py') and os.path.isfile(cmd[0]):
        cmd = [venv_python] + cmd

    # Wrap Python commands with bootstrap logging setup injected via -c.
    # This configures the root logger in the child process before any job code runs
    if cmd[0] == venv_python:
        rest = cmd[1:]
        if rest and rest[0] == '-m' and len(rest) >= 2:
            module, extra_argv = rest[1], rest[2:]
            cmd = [venv_python, '-c',
                   f"{_BOOTSTRAP};"
                   f"import runpy,sys;"
                   f"sys.argv=['{module}']+{extra_argv!r};"
                   f"runpy.run_module('{module}',run_name='__main__',alter_sys=True)"]
        elif rest and rest[0].endswith('.py') and os.path.isfile(rest[0]):
            script, extra_argv = rest[0].replace('\\', '/'), rest[1:]
            cmd = [venv_python, '-c',
                   f"{_BOOTSTRAP};"
                   f"import runpy,sys;"
                   f"sys.argv=['{script}']+{extra_argv!r};"
                   f"runpy.run_path('{script}',run_name='__main__')"]

    return cmd, child_env, script_root