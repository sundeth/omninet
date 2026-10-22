"""Contribution points and the Specials they buy, through the API.

Protects: the Digimon Database credits points by email, server to server,
with the shared secret; a credit is added once whatever how often it is sent
(idempotent by its key, also when the same key arrives twice at once); an
email with no account keeps its points until that account shows itself;
the balance is reported apart from the coins; Specials are synced from
specials.json, listed with their currency and their background's pictures,
bought from the right balance and downloaded with every picture; a
background cosmetic's download carries its files (it sent empty ones).

Runs only when ARENA_TEST_DATABASE_URL names a disposable database whose name
contains "test" (conftest.py; its user and shop tables are truncated).
"""
import asyncio
import base64
import json
import os
import uuid

import pytest

_DB_URL = os.environ.get("ARENA_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    "test" not in _DB_URL.rsplit("/", 1)[-1],
    reason="set ARENA_TEST_DATABASE_URL to a disposable *test* database")

TOKEN = "test-contribution-token"
CREDIT = "/api/v1/internal/contribution-points/credit"


def _png(tag: bytes) -> bytes:
    """Distinct bytes per file (the server never decodes them)."""
    return b"\x89PNG\r\n\x1a\n" + tag


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """A shop asset tree with one premium background and one plain one."""
    from omninet.config import settings
    monkeypatch.setattr(settings, "shop_assets_base", str(tmp_path))
    monkeypatch.setattr(settings, "contribution_service_token", TOKEN)
    backgrounds = tmp_path / "backgrounds"
    backgrounds.mkdir()
    files = {}
    for time in ("day", "dusk", "night"):
        for suffix in ("", "_high"):
            name = f"bg_premium_test_{time}{suffix}.png"
            files[name] = _png(name.encode())
    files["bg_plain.png"] = _png(b"plain")
    files["bg_plain_high.png"] = _png(b"plain high")
    for name, data in files.items():
        (backgrounds / name).write_bytes(data)
    specials = tmp_path / "specials"
    specials.mkdir()
    (specials / "specials.json").write_text(json.dumps({"specials": [
        {"id": str(uuid.UUID(int=2)), "name": "Coin Special", "price": 7,
         "type": "background", "sort_order": 2, "json": {"name": "plain"}},
        {"id": str(uuid.UUID(int=1)), "name": "Test Swamp", "price": 5,
         "currency": "contribution_points", "type": "background", "sort_order": 1,
         "description": "Day, dusk and night.",
         "json": {"name": "premium_test", "label": "Test Swamp"}},
        {"name": "Old Special", "price": 1, "end_date": "2020-01-01T00:00:00Z",
         "currency": "contribution_points", "type": "background",
         "json": {"name": "plain"}},
    ]}), encoding="utf-8")
    return tmp_path, files


async def _reset_database():
    from sqlalchemy import text

    from omninet.database import Base
    from omninet.database import engine as db_engine
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "TRUNCATE contribution_credits, user_purchases, shop_specials, shop_cosmetics, shop_items, "
            "game_battles, game_pets, game_teams, user_devices, activity_logs, reward_claims, "
            "users CASCADE"))


async def _account(nickname: str, email: str, coins: int = 0) -> tuple[str, str]:
    """A verified account with a device key: (user id, device key)."""
    from omninet.database import async_session_maker
    from omninet.services.device import DeviceService
    from omninet.services.user import UserService
    async with async_session_maker() as db:
        user = await UserService(db).create_user(
            nickname=nickname, email=email, password="pw", is_verified=True)
        user.coins = coins
        key = (await DeviceService(db).create_device(user.id)).secret_key
        await db.commit()
        return str(user.id), key


async def _balances(user_id: str) -> tuple[int, int]:
    from sqlalchemy import select

    from omninet.database import async_session_maker
    from omninet.models.user import User
    async with async_session_maker() as db:
        user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one()
        return user.coins, user.contribution_points


def _credit(key, email, points=1, reason="contribution"):
    return {"key": key, "email": email, "points": points, "reason": reason,
            "details": {"module": "DMC", "contribution": key}}


def _run(coroutine):
    """One event loop per test; the engine's pooled connections belong to
    it, so they are closed before it ends."""
    async def run():
        from omninet.database import engine as db_engine
        # A test before this one may have left connections of its own loop.
        await db_engine.dispose(close=False)
        try:
            await coroutine
        finally:
            await db_engine.dispose()
    asyncio.run(run())


def test_credits_are_by_email_once_per_key(storage):
    _run(_credits())


async def _credits():
    import httpx

    from omninet.config import settings
    from omninet.main import app

    await _reset_database()
    alice_id, alice_key = await _account("alice", "Alice@Test.local", coins=40)
    auth = {"X-Service-Token": TOKEN}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        body = {"credits": [_credit("db:DMC:1", "alice@test.local"),
                            _credit("db:DMC:2", "ALICE@test.local", 2, "data_needed")]}
        # The secret is required, and a server without one refuses everyone.
        assert (await api.post(CREDIT, json=body)).status_code == 403
        assert (await api.post(CREDIT, json=body,
                               headers={"X-Service-Token": "wrong"})).status_code == 403
        settings.contribution_service_token = ""
        assert (await api.post(CREDIT, json=body, headers=auth)).status_code == 503
        settings.contribution_service_token = TOKEN

        first = (await api.post(CREDIT, json=body, headers=auth)).json()
        assert (first["credited"], first["pending"], first["duplicate"]) == (2, 0, 0), first
        assert await _balances(alice_id) == (40, 3), "points are not coins"

        # A retry (an answer lost on the way back) adds nothing.
        again = (await api.post(CREDIT, json=body, headers=auth)).json()
        assert again["duplicate"] == 2 and again["credited"] == 0, again
        assert await _balances(alice_id) == (40, 3)

        # The same key sent five times at once is added once.
        racing = {"credits": [_credit("db:DMC:3", "alice@test.local")]}
        answers = await asyncio.gather(*[api.post(CREDIT, json=racing, headers=auth)
                                         for _ in range(5)])
        statuses = sorted(a.json()["results"][0]["status"] for a in answers)
        assert statuses == ["credited", "duplicate", "duplicate", "duplicate", "duplicate"], statuses
        assert await _balances(alice_id) == (40, 4)

        # Refused: more points than a credit may carry, or no email.
        too_many = {"credits": [_credit("db:DMC:4", "alice@test.local", 50)]}
        assert (await api.post(CREDIT, json=too_many, headers=auth)).status_code == 422
        not_email = {"credits": [_credit("db:DMC:5", "not an email")]}
        assert (await api.post(CREDIT, json=not_email, headers=auth)).status_code == 422
        assert await _balances(alice_id) == (40, 4)

        # The game reads the balance where it reads the coins.
        device = {"X-Device-Key": alice_key}
        me = (await api.post("/api/v1/auth/validate-device", headers=device)).json()
        assert (me["coins"], me["contribution_points"]) == (40, 4), me
        assert (await api.get("/api/v1/users/me", headers=device)).json()["contribution_points"] == 4
        assert (await api.get("/api/v1/auth/coins", headers=device)).json()["contribution_points"] == 4
        public = (await api.get("/api/v1/users/alice")).json()
        assert public["contribution_points"] == 0, "a public profile shows no balance"

        # No account has this email yet: the points wait for it ...
        waiting = {"credits": [_credit("db:DMC:6", "bob@test.local"),
                               _credit("db:DMH:1", "bob@test.local", 2)]}
        answer = (await api.post(CREDIT, json=waiting, headers=auth)).json()
        assert answer["pending"] == 2, answer
        # ... and reach it the first time it logs in.
        bob_id, bob_key = await _account("bob", "Bob@Test.local")
        me = (await api.post("/api/v1/auth/validate-device",
                             headers={"X-Device-Key": bob_key})).json()
        assert me["contribution_points"] == 3, me
        me = (await api.post("/api/v1/auth/validate-device",
                             headers={"X-Device-Key": bob_key})).json()
        assert me["contribution_points"] == 3, "pending points were claimed twice"
        assert (await api.post(CREDIT, json=waiting, headers=auth)).json()["duplicate"] == 2
        assert await _balances(bob_id) == (0, 3)


def test_specials_are_bought_with_their_own_currency(storage):
    _run(_specials(*storage))


async def _specials(root, files):
    import httpx

    from omninet.database import async_session_maker
    from omninet.main import app
    from omninet.models import CosmeticType, ShopCosmetic
    from omninet.services.shop_sync import sync_specials

    await _reset_database()
    async with async_session_maker() as db:
        assert await sync_specials(db, root / "specials" / "specials.json") == 3
        db.add(ShopCosmetic(id=uuid.UUID(int=9), cosmetic_type=CosmeticType.BACKGROUND,
                            name="Plain", price=3, json_data={"name": "plain"},
                            sprite_name="bg_plain", enabled=True))
        await db.commit()
    # The file got the id the sync gave the entry that had none.
    saved = json.loads((root / "specials" / "specials.json").read_text(encoding="utf-8"))
    assert all(entry.get("id") for entry in saved["specials"])

    user_id, key = await _account("carol", "carol@test.local", coins=20)
    device = {"X-Device-Key": key}
    swamp, coin_special = str(uuid.UUID(int=1)), str(uuid.UUID(int=2))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        listing = (await api.get("/api/v1/shop/specials")).json()
        names = [s["name"] for s in listing["specials"]]
        assert names == ["Test Swamp", "Coin Special"], "sort order, and an ended Special is off sale"
        first = listing["specials"][0]
        assert first["currency"] == "contribution_points" and first["price"] == 5
        assert first["special_type"] == "background" and first["sprite_name"] == "bg_premium_test"
        assert (first["day_night"], first["high_res"]) == (True, True)
        assert listing["specials"][1]["currency"] == "coins"
        assert (listing["specials"][1]["day_night"], listing["specials"][1]["high_res"]) == (False, True)

        # Previews: the day picture, high-resolution or (size=small) the game's.
        big = await api.get(f"/api/v1/shop/special/{swamp}/sprite")
        assert big.content == files["bg_premium_test_day_high.png"]
        small = await api.get(f"/api/v1/shop/special/{swamp}/sprite?size=small")
        assert small.content == files["bg_premium_test_day.png"]

        buy = {"purchase_type": "special", "item_id": swamp}
        refused = (await api.post("/api/v1/shop/purchase", json=buy, headers=device)).json()
        assert refused["success"] is False and "contribution points" in refused["message"], refused
        assert await _balances(user_id) == (20, 0), "coins were spent on a points Special"
        # Not downloadable before it is bought.
        assert (await api.get(f"/api/v1/shop/download/special/{swamp}",
                              headers=device)).status_code == 404

        async with async_session_maker() as db:
            from omninet.services.contribution import ContributionService
            for n in range(5):
                await ContributionService(db).credit(f"db:test:{n}", "carol@test.local", 1,
                                                     "digimon-database")
            await db.commit()
        bought = (await api.post("/api/v1/shop/purchase", json=buy, headers=device)).json()
        assert bought["success"] is True, bought
        assert bought["currency"] == "contribution_points"
        assert bought["contribution_points_remaining"] == 0
        assert bought["coins_remaining"] == 20
        assert await _balances(user_id) == (20, 0)
        again = (await api.post("/api/v1/shop/purchase", json=buy, headers=device)).json()
        assert again["success"] is False and "already own" in again["message"]

        download = (await api.get(f"/api/v1/shop/download/special/{swamp}",
                                  headers=device)).json()
        assert download["special_type"] == "background"
        assert (download["day_night"], download["high_res"]) == (True, True)
        got = {name: base64.b64decode(data) for name, data in download["sprites"].items()}
        assert got == {n: d for n, d in files.items() if n.startswith("bg_premium_test")}

        # A coin Special is paid with coins.
        coin = (await api.post("/api/v1/shop/purchase", headers=device,
                               json={"purchase_type": "special", "item_id": coin_special})).json()
        assert coin["success"] is True and coin["currency"] == "coins", coin
        assert coin["coins_remaining"] == 13 and coin["contribution_points_remaining"] is None
        assert await _balances(user_id) == (13, 0)

        purchases = (await api.get("/api/v1/shop/purchases", headers=device)).json()["purchases"]
        assert sorted((p["item_id"], p["currency"], p["price_paid"]) for p in purchases) == sorted(
            [(swamp, "contribution_points", 5), (coin_special, "coins", 7)])

        # A background cosmetic's download carries its pictures now.
        cosmetic = str(uuid.UUID(int=9))
        assert (await api.post("/api/v1/shop/purchase", headers=device, json={
            "purchase_type": "cosmetic", "item_id": cosmetic})).json()["success"] is True
        download = (await api.get(f"/api/v1/shop/download/cosmetic/{cosmetic}",
                                  headers=device)).json()
        got = {name: base64.b64decode(data) for name, data in download["sprites"].items()}
        assert got == {"bg_plain.png": files["bg_plain.png"],
                       "bg_plain_high.png": files["bg_plain_high.png"]}
