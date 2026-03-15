# Design Review: master.py

---

## What this is trying to do

master.py is a job runner. Given a config file and a command, it:
1. Loads config key/value pairs from a file and interpolates variables
2. Activates the right venv for the child process
3. Injects the resolved config as environment variables
4. Runs the child command as a subprocess with stdout/stderr streamed back

---

## context
- Hundreds of Rundeck jobs across mixed runtimes: Python 2, Python 3 with child venvs, Kornshell, Node, Java binaries, Bash, SQL, etc
- Zero external dependency freedom. Adding python-dotenv or uv requires months of auditor approval
- Dev on Windows, deploy to Oracle Linux 8. No Docker, no WSL, no VM
- Each job currently manages its own environment with no consistency, no shared logging, and no central inventory of what any job actually needs

---

## Concerns

---

### 3. parse_config_file is doing too much -- REVISED, keep it but test it

**Revised action:** Write unit tests for parse_config_file. This is the highest-value testing investment in the whole repo because it is load-bearing for every single job. A bad interpolation produces wrong credentials or wrong endpoints, and that failure might not surface until a job has already processed data against the wrong system.

---

### 4. Config vars are dumped wholesale into the child environment

```python
child_env = os.environ.copy()
child_env.update(config_vars)
```

Every key in your .env file becomes an environment variable in the child process. This is probably fine for secrets (that is the point), but it has two risks:

- A config key that happens to match a system env var (like `PATH`, `HOME`, `LANG`, `TZ`) will silently overwrite it in the child
- If the config file is ever logged or printed in debug mode, secrets are exposed

**Action:** Check for collisions against a known list of reserved env var names. Add a warning if a config key would overwrite an existing system variable.

---

## What master.py still needs for the real problem

### Runtime detection

Currently master.py only handles Python-like executables. A Rundeck job that is a ksh script or a Java binary needs to be dispatched differently. Consider a `--runtime` flag or detecting from file extension:

```
.py  -> venv python
.js  -> node
.sh / .ksh -> sh or ksh
.jar -> java -jar
no extension, executable -> run directly
```

This would let master.py be the single entry point for every job type in Rundeck without each job needing its own wrapper.

### Job manifest / registry

Right now the knowledge of what each job needs (which config file, which venv, which runtime, what env vars it expects) lives in Rundeck itself or in someone's head. There is no machine-readable record.

A simple JSON or ini file per job that declares its requirements would let you finally answer "what is in these jobs" without reading each one:

```json
{
  "job": "sf_sync",
  "runtime": "python",
  "venv": "./venvs/sf_sync",
  "config": "./configs/prod.env",
  "entry": "python -m jobs.sf_sync",
  "expects": ["CONSUMER_KEY", "CONSUMER_SECRET", "BASE_URL"]
}
```

master.py could validate that all expected env vars are present before launching, and fail fast with a clear error instead of letting the job crash mid-run with a missing key.

### Expected env var validation

Related to the above. Even without a manifest, `--require KEY1 KEY2` would let callers declare which vars must be present. If any are missing after config resolution, master.py exits before the child starts. This alone would have caught many silent failures in existing jobs.

### Cross-platform path normalization

The venv path resolution handles Windows vs Linux correctly for Python. For the ksh and Java cases, path separators and executable names will need the same treatment. Factor `get_venv_paths` into a more general `resolve_executable` that handles all runtime types.

---
