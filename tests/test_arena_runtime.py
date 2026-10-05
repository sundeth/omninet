"""Arena runtime store, engine invocation and schedule maths (no database)."""
from datetime import UTC, datetime, timedelta

import pytest
from conftest import TESTMON, make_module_zip

from omninet.arena import rules
from omninet.arena.engine import run_engine, verify_runtime
from omninet.arena.runtime import ArenaRuntime, RuntimeUpdateError, safe_module_name


def _queue_module_bytes(runtime: ArenaRuntime, name: str, data: bytes, tmp_path):
    source = tmp_path / f"{name}-upload.zip"
    source.write_bytes(data)
    return runtime.queue_module(name, source)


def test_a_module_alone_cannot_start_a_runtime(arena_root, tmp_path):
    runtime = ArenaRuntime(arena_root)
    _queue_module_bytes(runtime, "TESTMOD", make_module_zip("TESTMOD", [TESTMON]), tmp_path)
    report = runtime.apply_pending()
    assert "No Omnipet build" in report["error"]
    assert runtime.current() is None
    assert not runtime.has_pending()          # moved to rejected/
    assert (arena_root / "rejected").is_dir()


def test_updates_wait_in_the_drop_folder_until_applied(arena_root, tmp_path, omnipet_zip_bytes):
    runtime = ArenaRuntime(arena_root)
    runtime.queue_omnipet(omnipet_zip_bytes)
    _queue_module_bytes(runtime, "TESTMOD", make_module_zip("TESTMOD", [TESTMON]), tmp_path)
    assert runtime.pending()["modules"] == ["TESTMOD"]
    assert runtime.current() is None

    first = runtime.apply_pending(verify_runtime)
    assert "error" not in first, first
    live = runtime.current_dir()
    assert (live / "src" / "battle" / "arena" / "engine.py").is_file()
    assert first["modules"]["TESTMOD"] == "1.0.0"
    assert "DMC" in first["modules"]
    # Only data travels: no art, no bytecode.
    assert not list(live.rglob("*.png"))
    assert not list(live.rglob("__pycache__"))
    assert not runtime.has_pending()

    # A later module update builds a new snapshot; the old one is untouched.
    _queue_module_bytes(runtime, "TESTMOD",
                        make_module_zip("TESTMOD", [dict(TESTMON, power=99)], "1.0.1"), tmp_path)
    second = runtime.apply_pending(verify_runtime)
    assert second["version"] != first["version"]
    assert second["modules"]["TESTMOD"] == "1.0.1"
    assert runtime.dir_for(first["version"]) is not None
    assert (runtime.current_dir() / "src").is_dir()   # src carried over

    # Removal markers drop a module at the next rollover.
    runtime.queue_module_removal("TESTMOD")
    third = runtime.apply_pending(verify_runtime)
    assert "TESTMOD" not in third["modules"]
    assert not (runtime.current_dir() / "modules" / "TESTMOD").exists()


def test_unsafe_zip_members_never_leave_the_snapshot(arena_root, tmp_path, omnipet_zip_bytes):
    runtime = ArenaRuntime(arena_root)
    runtime.queue_omnipet(omnipet_zip_bytes)
    evil = make_module_zip("TESTMOD", [TESTMON], extra={
        "TESTMOD/../../escape.json": b"{}",
        "TESTMOD/sub/../../../escape2.json": b"{}",
    })
    _queue_module_bytes(runtime, "TESTMOD", evil, tmp_path)
    report = runtime.apply_pending(verify_runtime)
    assert "error" not in report, report
    assert not list(arena_root.rglob("escape*.json"))


def test_module_names_are_checked(arena_root):
    for bad in ("../x", "a/b", "", ".", "x" * 200):
        with pytest.raises(RuntimeUpdateError):
            safe_module_name(bad)
    assert safe_module_name("D-3") == "D-3"


def test_a_build_without_the_engine_is_refused(arena_root):
    runtime = ArenaRuntime(arena_root)
    with pytest.raises(RuntimeUpdateError):
        runtime.queue_omnipet(make_module_zip("NOTOMNIPET", [TESTMON]))


def test_the_engine_rebuilds_uploads_from_server_data(arena_root, tmp_path, omnipet_zip_bytes):
    runtime = ArenaRuntime(arena_root)
    runtime.queue_omnipet(omnipet_zip_bytes)
    _queue_module_bytes(runtime, "TESTMOD", make_module_zip("TESTMOD", [TESTMON]), tmp_path)
    runtime.apply_pending(verify_runtime)
    live = runtime.current_dir()

    upload = {"module_name": "TESTMOD", "name": "Testmon", "pet_version": 1,
              # Main stats from the client are ignored; status is clamped.
              "power": 9999, "attribute": "Vi", "stage": 7,
              "status": {"level": 50, "strength": 99}}
    answer = run_engine(live, {"command": "validate_team", "pets": [upload] * 3})
    assert answer["ok"], answer
    entry = answer["entries"][0]
    assert (entry["power"], entry["attribute"], entry["stage"]) == (40, "Va", 4)
    assert entry["level"] == 6 and entry["status"]["strength"] == 4

    refused = run_engine(live, {"command": "validate_team", "pets": [
        dict(upload, module_name="NOT_ON_SERVER")] + [upload] * 2})
    assert not refused["ok"]
    assert refused["errors"][0]["code"] == "module_unavailable"

    restricted = run_engine(live, {"command": "validate_team", "pets": [upload] * 3,
                                   "restrictions": {"allowed_attributes": ["Virus"]}})
    assert not restricted["ok"] and restricted["errors"][0]["code"] == "restricted"


def test_auto_slots_tile_from_the_anchor():
    anchor = datetime(2026, 1, 4, tzinfo=UTC)          # a Sunday
    week = timedelta(days=7)
    now = datetime(2026, 10, 7, 15, 30, tzinfo=UTC)    # a Wednesday
    start, end = rules.auto_slot(now, anchor, week)
    assert start == datetime(2026, 10, 4, tzinfo=UTC)
    assert end - start == week and start <= now < end
    assert rules.auto_season_name(start, now, week) == "Week of October 04, 2026"

    hour = timedelta(hours=1)
    start, end = rules.auto_slot(now, anchor, hour)
    assert (start, end) == (now.replace(minute=0), now.replace(minute=0) + hour)


def test_season_config_overrides_only_known_keys():
    class Season:
        config = {"attacks_per_day": "20", "charge": "random", "bogus": 1}
    config = rules.season_config(Season())
    assert config["attacks_per_day"] == 20 and config["charge"] == "random"
    assert "bogus" not in config
    assert rules.clean_config({"charge": 9})["charge"] == 3


def test_the_attack_day_starts_at_midnight_or_the_season_start():
    now = datetime(2026, 10, 5, 18, tzinfo=UTC)
    assert rules.attack_day_start(now, None) == datetime(2026, 10, 5, tzinfo=UTC)
    later = datetime(2026, 10, 5, 12, tzinfo=UTC)
    assert rules.attack_day_start(now, later) == later
