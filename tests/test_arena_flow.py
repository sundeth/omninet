"""A whole arena season through the API, on a disposable Postgres database.

Runs only when ARENA_TEST_DATABASE_URL names a database whose name contains
"test": every arena, user and log table in it is truncated.
"""
import asyncio
import io
import json
import os
import shutil
import sys
import zipfile
from datetime import timedelta

import pytest
from conftest import DEV_TOKEN, OMNIPET_ROOT

_DB_URL = os.environ.get("ARENA_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    "test" not in _DB_URL.rsplit("/", 1)[-1],
    reason="set ARENA_TEST_DATABASE_URL to a disposable *test* database")


def _module_zip_from_checkout(name: str, version: str) -> bytes:
    """The checkout's module JSON, re-versioned, as a module editor zip."""
    folder = OMNIPET_ROOT / "modules" / name
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        meta = json.loads((folder / "module.json").read_text(encoding="utf-8"))
        meta["version"] = version
        zf.writestr(f"{name}/module.json", json.dumps(meta))
        zf.writestr(f"{name}/monster.json", (folder / "monster.json").read_text(encoding="utf-8"))
    return buffer.getvalue()


def test_a_full_season(omnipet_zip_bytes, tmp_path):
    asyncio.run(_season(omnipet_zip_bytes, tmp_path))


async def _season(omnipet_zip_bytes, tmp_path):
    import httpx
    from sqlalchemy import select, text

    from omninet.arena.engine import run_engine
    from omninet.arena.runtime import ArenaRuntime
    from omninet.config import settings
    from omninet.database import async_session_maker
    from omninet.database import engine as db_engine
    from omninet.main import app
    from omninet.models.battle import GamePet, GameTeam
    from omninet.services.device import DeviceService
    from omninet.services.season import SeasonService
    from omninet.services.user import UserService

    sys.path.insert(0, str(OMNIPET_ROOT / "src"))
    from battle.arena import replay as arena_replay  # the game's replay reader

    shutil.rmtree(settings.arena_path, ignore_errors=True)
    async with db_engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE game_battles, game_pets, game_teams, seasons, user_devices, "
            "activity_logs, reward_claims, users CASCADE"))

    # -- the first runtime installs at once and the clock opens a season ----
    ArenaRuntime().queue_omnipet(omnipet_zip_bytes)
    async with async_session_maker() as db:
        report = await SeasonService(db).tick(wait_for_lock=True)
        await db.commit()
    assert "error" not in report["runtime"], report
    assert "opened" in report, report
    first_runtime = ArenaRuntime().current()["version"]

    async with async_session_maker() as db:
        user = await UserService(db).create_user(
            nickname="alice", email="alice@test.local", password="pw",
            is_verified=True)
        key = (await DeviceService(db).create_device(user.id)).secret_key
        await db.commit()
    auth = {"X-Device-Key": key}

    dev = {"X-Dev-Token": DEV_TOKEN}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        modules = (await api.get("/api/v1/arena/modules")).json()
        assert "DMC" in {m["name"] for m in modules["modules"]}

        season = (await api.get("/api/v1/seasons/current")).json()
        assert season["config"]["attacks_per_day"] == settings.max_daily_battles
        assert season["runtime_version"] == first_runtime

        # The dev tools are closed without an admin key or the dev token.
        locked = await api.post("/api/v1/dev/arena/dummies", json={"count": 1})
        assert locked.status_code == 403
        player = await api.post("/api/v1/dev/arena/dummies", json={"count": 1}, headers=auth)
        assert player.status_code == 403
        dummies = (await api.post("/api/v1/dev/arena/dummies",
                                  json={"count": 6, "seed": 1}, headers=dev)).json()
        assert len(dummies["created"]) == 6, dummies

        # -- a player's team: species from the server, status clamped -------
        uploads = run_engine(ArenaRuntime().current_dir(), {
            "command": "random_team", "seed": 42,
            "restrictions": {"allowed_modules": ["DMC"]}})["pets"]
        refused = await api.post("/api/v1/teams", headers=auth, json={
            "pets": [dict(uploads[0], module_name="NOT_ON_SERVER")] + uploads[1:]})
        assert refused.status_code == 400
        assert "not available" in refused.json()["detail"]

        tampered = [dict(u, power=9999, stage=7, attribute="Vi") for u in uploads]
        created = await api.post("/api/v1/teams", headers=auth, json={"pets": tampered})
        assert created.status_code == 200, created.text
        team = created.json()
        assert team["season_ends_at"] and team["daily_battles_remaining"] == settings.max_daily_battles
        assert all(p["power"] < 9999 and p["stage"] != 7 for p in team["pets"])

        # -- attacking: replayable log, attacks counted, defences free ------
        found = (await api.post(f"/api/v1/battles/find/{team['id']}", headers=auth)).json()
        assert found["battle_found"], found
        battle = found["battle"]
        log = battle["battle_log"]
        assert log["version"] == arena_replay.LOG_VERSION
        assert log["attacker"]["team_id"] == team["id"]
        assert log["winner"] in ("device1", "device2", "draw")
        mine, theirs, result, my_hp, their_hp = arena_replay.viewer_side(log, True)
        assert len(mine["pets"]) == 3 and my_hp == log["hp"]["team1"]
        _, _, as_defender, _, _ = arena_replay.viewer_side(log, False)
        assert as_defender["device1_final"] == result["device2_final"]

        bots = (await api.post("/api/v1/dev/arena/bots/run", json={"battles": 12, "seed": 3},
                               headers=dev)).json()
        assert bots["battles"] >= 1, bots
        current = (await api.get("/api/v1/teams/current", headers=auth)).json()
        assert current["daily_battles_remaining"] == settings.max_daily_battles - 1

        history = (await api.get(f"/api/v1/battles/team/{team['id']}/history",
                                 headers=auth)).json()
        assert {"attack"} <= {b["role"] for b in history["battles"]}
        watched = (await api.get(f"/api/v1/battles/{battle['id']}", headers=auth)).json()
        assert watched["battle_log"]["seed"] == log["seed"]

        # -- updates wait for the season boundary ---------------------------
        source = tmp_path / "DMC.zip"
        source.write_bytes(_module_zip_from_checkout("DMC", "9.9.9"))
        ArenaRuntime().queue_module("DMC", source)
        async with async_session_maker() as db:
            await SeasonService(db).tick(wait_for_lock=True)
            await db.commit()
        assert ArenaRuntime().current()["version"] == first_runtime
        early = (await api.post("/api/v1/teams/claim-rewards", headers=auth)).json()
        assert early["teams_processed"] == 0

        ended = (await api.post("/api/v1/dev/arena/season/end",
                                json={"start_next": True}, headers=dev)).json()
        assert ended["report"]["closed"], ended
        assert ended["report"]["runtime"]["modules"]["DMC"] == "9.9.9"
        assert ended["status"]["season"]["runtime_version"] != first_runtime

        past = (await api.get("/api/v1/teams?include_past=true", headers=auth)).json()
        mine_past = next(t for t in past if t["id"] == team["id"])
        assert mine_past["season_status"] == "completed" and mine_past["final_rank"]
        claim = (await api.post("/api/v1/teams/claim-rewards", headers=auth)).json()
        assert claim["teams_processed"] == 1
        assert claim["coins_claimed"] == mine_past["rewarded_coins"]
        again = (await api.post("/api/v1/teams/claim-rewards", headers=auth)).json()
        assert again["teams_processed"] == 0

        # -- a forced themed season, minutes long ---------------------------
        themed = (await api.post("/api/v1/dev/arena/season/start", json={
            "length_hours": 0.25,
            "restrictions": {"allowed_stages": [3]},
            "config": {"attacks_per_day": 50, "charge": "random"},
        }, headers=dev)).json()
        assert themed["season"]["config"]["charge"] == "random"
        wrong = await api.post("/api/v1/teams", headers=auth, json={"pets": tampered})
        assert wrong.status_code == 400 and "Stage" in wrong.json()["detail"]
        dummies = (await api.post("/api/v1/dev/arena/dummies",
                                  json={"count": 4, "seed": 2}, headers=dev)).json()
        assert len(dummies["created"]) == 4, dummies
        async with async_session_maker() as db:
            stages = (await db.execute(
                select(GamePet.stage).join(GameTeam, GamePet.team_id == GameTeam.id)
                .where(GameTeam.season_id == themed["season"]["id"]))).scalars().all()
        assert stages and set(stages) == {3}
        idle = (await api.post("/api/v1/dev/arena/season/end",
                               json={"start_next": False}, headers=dev)).json()
        assert idle["report"]["closed"]["prizes"] == 0   # nobody fought
        assert idle["status"]["season"] is None

    # -- with no season running the clock opens one; when its time is up it
    # closes it on its own and opens the next ---------------------------------
    async with async_session_maker() as db:
        service = SeasonService(db)
        assert "opened" in await service.tick(wait_for_lock=True)
        running = await service.get_active_season()
        report = await service.tick(now=running.ends_at + timedelta(seconds=1),
                                    wait_for_lock=True)
        await db.commit()
    assert report["closed"]["id"] == str(running.id) and "opened" in report, report

    await db_engine.dispose()
