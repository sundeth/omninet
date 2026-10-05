"""
Running Omnipet's arena engine from a runtime snapshot.

The engine is ``python -m battle.arena`` inside the snapshot's ``src/``: one
JSON request on stdin, one JSON answer on stdout (see Omnipet's
``battle/arena/engine.py``). It runs in its own process so each season's
code stays isolated from the server and from other seasons' code.
"""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from omninet.arena.runtime import ArenaRuntime
from omninet.config import settings

#: Engine contract versions this server understands.
SUPPORTED_ENGINE_VERSIONS = {1}


class EngineError(Exception):
    """The engine refused a request or could not run."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def run_engine(runtime_dir: Path, request: dict, timeout: float | None = None) -> dict:
    """Run one request synchronously; returns the engine's answer."""
    src = runtime_dir / "src"
    request = dict(request)
    request.setdefault("modules_dir", str(runtime_dir / "modules"))
    env = dict(os.environ,
               PYTHONPATH=str(src),
               PYTHONDONTWRITEBYTECODE="1",
               PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run(
            [settings.arena_python or sys.executable, "-B", "-m", "battle.arena"],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(src),
            env=env,
            timeout=timeout or settings.arena_engine_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise EngineError("engine_timeout", "The arena engine timed out") from exc
    except OSError as exc:
        raise EngineError("engine_failure", f"Could not start the arena engine: {exc}") from exc
    try:
        answer = json.loads(proc.stdout)
    except ValueError as exc:
        tail = (proc.stderr or "")[-800:]
        raise EngineError("engine_failure",
                          f"Arena engine exited {proc.returncode}: {tail}") from exc
    return answer


def verify_runtime(runtime_dir: Path) -> None:
    """Raise unless the engine runs from *runtime_dir* and reads its modules."""
    info = run_engine(runtime_dir, {"command": "info"})
    if not info.get("ok") or info.get("engine_version") not in SUPPORTED_ENGINE_VERSIONS:
        raise EngineError("engine_version",
                          f"Unsupported arena engine: {info.get('engine_version')!r}")
    catalog = run_engine(runtime_dir, {"command": "catalog"})
    if not catalog.get("ok"):
        raise EngineError(catalog.get("error", "engine_failure"),
                          catalog.get("message", "catalog failed"))


def runtime_dir_for(version: str | None) -> Path:
    """The snapshot a season fights on: its own, else the live one."""
    runtime = ArenaRuntime()
    path = runtime.dir_for(version) or runtime.current_dir()
    if path is None:
        raise EngineError("no_runtime", "The arena has no Omnipet runtime installed yet")
    return path


async def call(request: dict, runtime_version: str | None = None,
               *, raise_on_refusal: bool = True) -> dict:
    """Run one engine request off the event loop.

    With *raise_on_refusal* an ``ok: false`` answer becomes an EngineError;
    ``validate_team`` callers pass False to read the per-pet errors.
    """
    path = runtime_dir_for(runtime_version)
    answer = await asyncio.to_thread(run_engine, path, request)
    if raise_on_refusal and not answer.get("ok"):
        raise EngineError(answer.get("error", "engine_failure"),
                          answer.get("message", "The arena engine refused the request"))
    return answer


_catalog_cache: dict[str, dict] = {}


async def catalog(runtime_version: str | None = None) -> dict:
    """Modules on a snapshot (cached: a snapshot never changes)."""
    path = runtime_dir_for(runtime_version)
    key = str(path)
    if key not in _catalog_cache:
        _catalog_cache[key] = await call({"command": "catalog"}, path.name)
    return _catalog_cache[key]
