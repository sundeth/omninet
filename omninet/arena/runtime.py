"""
Arena runtimes: the server's copy of Omnipet and its modules.

Battles are fought by Omnipet's own engine (``python -m battle.arena``) run
from a snapshot of Omnipet's source and module data that the server keeps.
A snapshot never changes while a season runs: updates wait in a drop folder
and are applied when the season ends, so rules cannot change mid-season.

Layout under ``settings.arena_storage_path``::

    updates/                    drop folder, read when a season ends
        omnipet*.zip            an Omnipet build: src/ and optionally modules/
        modules/<NAME>.zip      module updates (module publishing queues them)
        modules/<NAME>.remove   marker: drop that module at the next rollover
    runtimes/<version>/         one snapshot: src/ (.py/.json), modules/<NAME>/ (.json)
    runtimes/current.json       which snapshot is live, and what it contains
    applied/<version>/          the update files a snapshot consumed
    rejected/<version>/         updates whose snapshot failed verification

Only ``.py`` and ``.json`` files are taken from an Omnipet build and only
``.json`` from a module: battles need no art, and nothing a module ships is
executed.
"""
import json
import os
import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from omninet.config import settings

#: A file that marks an Omnipet build carrying this engine.
ENGINE_MARKER = "src/battle/arena/engine.py"

_MODULE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,99}$")
_MAX_MEMBER_BYTES = 64 * 1024 * 1024
_SKIP_DIRS = {"__pycache__", "documentation", ".git"}


class RuntimeUpdateError(Exception):
    """An update that cannot be applied."""


def _now_version() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")


def safe_module_name(name: str) -> str:
    """*name* if it is safe as a folder/file name, else RuntimeUpdateError."""
    name = (name or "").strip()
    if not _MODULE_NAME.match(name) or name in (".", ".."):
        raise RuntimeUpdateError(f"Unusable module name: {name!r}")
    return name


def _member_parts(filename: str, prefix: str) -> list[str] | None:
    """The path parts of a zip member below *prefix*, or None to skip it."""
    name = filename.replace("\\", "/")
    if not name.startswith(prefix) or name.endswith("/"):
        return None
    parts = PurePosixPath(name[len(prefix):]).parts
    if not parts or any(p in ("", ".", "..") or ":" in p for p in parts):
        return None
    if any(p in _SKIP_DIRS for p in parts[:-1]):
        return None
    return list(parts)


def _extract(zf: zipfile.ZipFile, prefix: str, dest: Path, suffixes: tuple[str, ...]) -> int:
    """Extract members below *prefix* with one of *suffixes* into *dest*."""
    count = 0
    dest = dest.resolve()
    for info in zf.infolist():
        parts = _member_parts(info.filename, prefix)
        if parts is None or not parts[-1].lower().endswith(suffixes):
            continue
        if info.file_size > _MAX_MEMBER_BYTES:
            raise RuntimeUpdateError(f"{info.filename} is too large")
        target = dest.joinpath(*parts).resolve()
        if dest not in target.parents:
            raise RuntimeUpdateError(f"Unsafe path in zip: {info.filename}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)
        count += 1
    return count


def _module_prefix(zf: zipfile.ZipFile) -> tuple[str, dict]:
    """(folder prefix, module.json) of a module zip: its shallowest module.json."""
    candidates = sorted(
        (n.replace("\\", "/") for n in zf.namelist()
         if n.replace("\\", "/").rsplit("/", 1)[-1] == "module.json"),
        key=lambda n: n.count("/"))
    if not candidates:
        raise RuntimeUpdateError("module.json not found in zip")
    with zf.open(candidates[0]) as f:
        meta = json.load(f)
    prefix = candidates[0][: -len("module.json")]
    return prefix, meta


def _omnipet_prefix(zf: zipfile.ZipFile) -> str:
    """The folder inside an Omnipet zip that holds src/."""
    for name in zf.namelist():
        name = name.replace("\\", "/")
        if name.endswith(ENGINE_MARKER):
            return name[: -len(ENGINE_MARKER)]
    raise RuntimeUpdateError(f"Not an Omnipet build with the arena engine ({ENGINE_MARKER} missing)")


def _make_writable(path: Path) -> None:
    """Open *path* to every user, if this process owns it."""
    try:
        if path.stat().st_mode & 0o777 != 0o777:
            os.chmod(path, 0o777)
    except OSError:
        pass  # someone else's folder: whoever made it decides


def _write_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class ArenaRuntime:
    """The runtime store. Methods are synchronous file operations; callers
    on the event loop run them with ``asyncio.to_thread``."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else settings.arena_path
        self.updates_dir = self.root / "updates"
        self.module_updates_dir = self.updates_dir / "modules"
        self.runtimes_dir = self.root / "runtimes"
        self.applied_dir = self.root / "applied"
        self.rejected_dir = self.root / "rejected"
        for path in (self.module_updates_dir, self.runtimes_dir):
            path.mkdir(parents=True, exist_ok=True)
        # The drop folders are filled by hand over the host's file share,
        # whose user is not the container's: let anyone who can reach the
        # folder write there.  The share is the access control.
        for path in (self.updates_dir, self.module_updates_dir):
            _make_writable(path)

    # -- current snapshot -------------------------------------------------

    @property
    def _current_file(self) -> Path:
        return self.runtimes_dir / "current.json"

    def current(self) -> dict | None:
        """The live snapshot's manifest, or None before the first one."""
        try:
            manifest = json.loads(self._current_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not (self.runtimes_dir / manifest.get("version", "")).is_dir():
            return None
        return manifest

    def dir_for(self, version: str | None) -> Path | None:
        """The snapshot folder for *version*, or None if it is gone."""
        if not version or "/" in version or "\\" in version or version.startswith("."):
            return None
        path = self.runtimes_dir / version
        return path if path.is_dir() else None

    def current_dir(self) -> Path | None:
        manifest = self.current()
        return self.dir_for(manifest["version"]) if manifest else None

    # -- the drop folder --------------------------------------------------

    def pending(self) -> dict:
        """What the next rollover would apply."""
        omnipet = sorted(p.name for p in self.updates_dir.glob("omnipet*.zip"))
        modules = sorted(p.stem for p in self.module_updates_dir.glob("*.zip"))
        removals = sorted(p.stem for p in self.module_updates_dir.glob("*.remove"))
        return {"omnipet": omnipet, "modules": modules, "removals": removals}

    def has_pending(self) -> bool:
        return any(self.pending().values())

    def queue_omnipet(self, data: bytes) -> Path:
        """Drop an Omnipet build zip; checked now, applied at the next rollover."""
        import io
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            _omnipet_prefix(zf)
        path = self.updates_dir / f"omnipet-{_now_version()}.zip"
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return path

    def queue_module(self, name: str, source: Path | str) -> Path:
        """Queue a published module zip as ``updates/modules/<name>.zip``.

        A newer queued zip replaces an older one; it also cancels a pending
        removal of the same module.
        """
        name = safe_module_name(name)
        path = self.module_updates_dir / f"{name}.zip"
        tmp = path.with_suffix(".part")
        shutil.copyfile(source, tmp)
        os.replace(tmp, path)
        (self.module_updates_dir / f"{name}.remove").unlink(missing_ok=True)
        return path

    def queue_module_removal(self, name: str) -> None:
        """Drop *name* from the arena at the next rollover (e.g. a ban)."""
        name = safe_module_name(name)
        (self.module_updates_dir / f"{name}.zip").unlink(missing_ok=True)
        (self.module_updates_dir / f"{name}.remove").write_text(
            datetime.now(UTC).isoformat(), encoding="utf-8")

    # -- applying ----------------------------------------------------------

    def apply_pending(self, verify=None) -> dict | None:
        """Build a new snapshot from the live one plus everything queued.

        *verify* is called with the new snapshot folder and must raise when
        the engine cannot run from it; the snapshot is then discarded and
        its updates moved to ``rejected/``. Returns the new manifest, a dict
        with ``error`` when rejected, or None when nothing was queued.
        """
        current = self.current()
        omnipet_zips = sorted(self.updates_dir.glob("omnipet*.zip"),
                              key=lambda p: p.stat().st_mtime)
        module_zips = sorted(self.module_updates_dir.glob("*.zip"))
        removals = sorted(self.module_updates_dir.glob("*.remove"))
        if not (omnipet_zips or module_zips or removals):
            return None

        for stale in self.runtimes_dir.glob("*.building"):
            shutil.rmtree(stale, ignore_errors=True)
        version = _now_version()
        building = self.runtimes_dir / f"{version}.building"
        consumed = omnipet_zips + module_zips + removals
        try:
            if current:
                shutil.copytree(self.runtimes_dir / current["version"], building)
            else:
                building.mkdir(parents=True)
            manifest = {
                "version": version,
                "applied_at": datetime.now(UTC).isoformat(),
                "omnipet": (current or {}).get("omnipet"),
                "modules": dict((current or {}).get("modules") or {}),
            }

            if omnipet_zips:
                # Only the newest build counts; older ones are just consumed.
                newest = omnipet_zips[-1]
                with zipfile.ZipFile(newest) as zf:
                    prefix = _omnipet_prefix(zf)
                    shutil.rmtree(building / "src", ignore_errors=True)
                    _extract(zf, prefix + "src/", building / "src", (".py", ".json"))
                    # Modules bundled with the build; queued module zips
                    # below still win over these.
                    bundled = sorted({
                        n.replace("\\", "/")[len(prefix) + len("modules/"):].split("/", 1)[0]
                        for n in zf.namelist()
                        if n.replace("\\", "/").startswith(prefix + "modules/")
                        and n.replace("\\", "/").endswith("/module.json")
                        and n.replace("\\", "/")[len(prefix) + len("modules/"):].count("/") == 1
                    })
                    for folder in bundled:
                        meta_name = f"{prefix}modules/{folder}/module.json"
                        with zf.open(meta_name) as f:
                            meta = json.load(f)
                        name = safe_module_name(meta.get("name") or folder)
                        shutil.rmtree(building / "modules" / name, ignore_errors=True)
                        _extract(zf, f"{prefix}modules/{folder}/",
                                 building / "modules" / name, (".json",))
                        manifest["modules"][name] = str(meta.get("version", "1.0"))
                manifest["omnipet"] = newest.name

            for path in module_zips:
                with zipfile.ZipFile(path) as zf:
                    prefix, meta = _module_prefix(zf)
                    name = safe_module_name(meta.get("name") or path.stem)
                    shutil.rmtree(building / "modules" / name, ignore_errors=True)
                    _extract(zf, prefix, building / "modules" / name, (".json",))
                    manifest["modules"][name] = str(meta.get("version", "1.0"))

            for marker in removals:
                name = safe_module_name(marker.stem)
                shutil.rmtree(building / "modules" / name, ignore_errors=True)
                manifest["modules"].pop(name, None)

            if not (building / ENGINE_MARKER.replace("/", os.sep)).is_file():
                raise RuntimeUpdateError("No Omnipet build has been supplied yet")
            if verify is not None:
                verify(building)
        except Exception as exc:  # noqa: BLE001 - every failure rejects the batch
            shutil.rmtree(building, ignore_errors=True)
            self._archive(consumed, self.rejected_dir / version)
            return {"error": str(exc), "rejected": [p.name for p in consumed]}

        final = self.runtimes_dir / version
        os.replace(building, final)
        _write_json_atomic(self._current_file, manifest)
        self._archive(consumed, self.applied_dir / version)
        self._prune(keep=manifest["version"])
        return manifest

    def _archive(self, paths: list[Path], dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        for path in paths:
            if path.exists():
                os.replace(path, dest / path.name)

    def _prune(self, keep: str) -> None:
        snapshots = sorted(p for p in self.runtimes_dir.iterdir()
                           if p.is_dir() and not p.name.endswith(".building"))
        excess = [p for p in snapshots if p.name != keep][: max(
            0, len(snapshots) - max(1, settings.arena_runtimes_to_keep))]
        for path in excess:
            shutil.rmtree(path, ignore_errors=True)
