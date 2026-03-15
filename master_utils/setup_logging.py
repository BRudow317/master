from __future__ import annotations

import sys, logging
from datetime import datetime
from pathlib import Path
import os

_program_name=os.getenv('PROGRAM_NAME', '')

_LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'


def setup_child_logging() -> None:
    """Configure root logger from LOG_LEVEL env var.
    Call this at the top of any child script run via master.py.
    master.py injects LOG_LEVEL into the child environment based on the -v flag.
    """
    level_name = os.getenv('LOG_LEVEL', 'WARNING').upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(level=level, stream=sys.stdout, format=_LOG_FORMAT, force=True)


def setup_logging(
        log_dir: str = "sys.stdout",
        verbose: bool = True,
        program_name: str = _program_name
        ) -> tuple[logging.Logger, Path | None]:
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(_LOG_FORMAT)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    logfile: Path | None = None
    if log_dir and log_dir != 'sys.stdout':
        path = Path(log_dir)
        path.mkdir(parents=True, exist_ok=True)
        logfile = path / f"{datetime.now():%Y_%m_%d_%H_%M_%S}_{program_name}.log"
        fh = logging.FileHandler(logfile)
        fh.setFormatter(formatter)
        root.addHandler(fh)
    
    return logging.getLogger(program_name), logfile