"""
Test setup for the arena.

Settings are read once, at the first import of omninet, so the environment
is fixed here before any test module imports it.  The arena store and module
storage live in a temporary folder.

The season-flow tests need Postgres: set ARENA_TEST_DATABASE_URL to a
disposable database whose name contains "test" (its tables are truncated).
Runtime tests need an Omnipet checkout: OMNIPET_ROOT (default ../Omnipet).
"""
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="omninet-arena-test-"))
os.environ["ENVIRONMENT"] = "dev"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ARENA_STORAGE_PATH"] = str(_TMP / "arena")
os.environ["MODULES_STORAGE_PATH"] = str(_TMP / "modules")
os.environ["ARENA_SEASON_LENGTH_HOURS"] = "1"
os.environ["ARENA_SEASON_RESTRICTIONS"] = ""
os.environ["ARENA_SEASON_CONFIG"] = ""
os.environ["ARENA_DEV_TOKEN"] = DEV_TOKEN = "test-dev-token"
os.environ["DATABASE_URL"] = os.environ.get(
    "ARENA_TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:1/never_connected_test")

OMNIPET_ROOT = Path(os.environ.get(
    "OMNIPET_ROOT", Path(__file__).resolve().parents[2] / "Omnipet"))
TEST_MODULES = ("DMC", "DMX", "DM20")


def _zip_tree(zf: zipfile.ZipFile, root: Path, base: Path, suffixes: tuple[str, ...]) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in suffixes and "__pycache__" not in path.parts:
            zf.write(path, path.relative_to(base).as_posix())


@pytest.fixture(scope="session")
def omnipet_zip_bytes() -> bytes:
    """An Omnipet build: src/ plus a few modules' JSON."""
    if not (OMNIPET_ROOT / "src" / "battle" / "arena" / "engine.py").is_file():
        pytest.skip(f"no arena-capable Omnipet checkout at {OMNIPET_ROOT}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        _zip_tree(zf, OMNIPET_ROOT / "src", OMNIPET_ROOT, (".py", ".json"))
        for name in TEST_MODULES:
            folder = OMNIPET_ROOT / "modules" / name
            if folder.is_dir():
                _zip_tree(zf, folder, OMNIPET_ROOT, (".json",))
    return buffer.getvalue()


def make_module_zip(name: str, monsters: list[dict], version: str = "1.0.0",
                    extra: dict[str, bytes] | None = None) -> bytes:
    """A minimal module zip, laid out as the module editor publishes it."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(f"{name}/module.json", json.dumps({
            "name": name, "version": version, "power_bonus_rule": "None",
            "visible_stats": "Level,Power"}))
        zf.writestr(f"{name}/monster.json", json.dumps({"monster": monsters}))
        zf.writestr(f"{name}/sprites/Testmon.png", b"\x89PNG not really")
        for member, data in (extra or {}).items():
            zf.writestr(member, data)
    return buffer.getvalue()


TESTMON = {
    "name": "Testmon", "version": 1, "stage": 4, "attribute": "Va", "power": 40,
    "hp": 12, "star": 0, "stomach": 4, "min_weight": 10, "atk_main": 3,
    "atk_alt": 4, "special": False, "index": 1,
}


@pytest.fixture
def arena_root(tmp_path) -> Path:
    return tmp_path / "arena"
