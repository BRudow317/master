#!/usr/bin/env python3
from __future__ import annotations

import os
import sys, subprocess, threading
from typing import IO, TextIO
from master_utils.parse_args import parse_args
from master_utils.setup_logging import setup_logging
from master_utils.child_env_setup import reexec_into_venv_if_needed, prepare_child
from master_utils.parse_config_file import parse_config_file


PROGRAM_NAME='master'
os.environ["PROGRAM_NAME"] = PROGRAM_NAME


def main():

    args, passthrough_args = parse_args(sys.argv[1:])
    logger, logfile = setup_logging(args.log_dir, args.verbose, PROGRAM_NAME)
    logger.debug(f"\nStarting {PROGRAM_NAME} with args: {args} and passthrough_args: {passthrough_args} \n\n\n")
    reexec_into_venv_if_needed(args)
    config_vars = parse_config_file(args.config, env=args.env) if args.config else {}
    cmd, child_env, child_cwd = prepare_child(args, config_vars)
    cmd.extend(passthrough_args)
    logger.debug(f"Child working directory: {child_cwd}")

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=child_env, cwd=child_cwd)
    assert process.stdout is not None
    assert process.stderr is not None

    log_lock = threading.Lock()
    lf = open(logfile, "a", encoding="utf-8") if logfile else None

    def stream_pipe(pipe: IO[bytes], out_stream: TextIO) -> None:
        for line in iter(pipe.readline, b""):
            text = line.decode("utf-8", errors="replace")
            out_stream.write(text)
            out_stream.flush()
            if lf:
                with log_lock:
                    lf.write(text)
                    lf.flush()
        pipe.close()

    t_out = threading.Thread(target=stream_pipe, args=(process.stdout, sys.stdout))
    t_err = threading.Thread(target=stream_pipe, args=(process.stderr, sys.stderr))
    t_out.start(); t_err.start(); t_out.join(); t_err.join()
    if lf:
        lf.close()
    process.wait()
    sys.exit( process.returncode )

if __name__ == '__main__':
    main()