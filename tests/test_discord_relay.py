"""The Discord relay (omninet/discord): its stores, its HTTP API, and that it
loads only with a token. No database and no Discord connection needed."""
import os
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omninet.discord import relay as relay_module
from omninet.discord.relay import ChannelRooms, GameRooms, LinkStore, Relay


@pytest.fixture
def relay(tmp_path, monkeypatch):
    r = Relay(str(tmp_path))
    monkeypatch.setattr(relay_module, "_relay", r)
    return r


@pytest.fixture
def client(relay):
    from omninet.routes.discord import router
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_links_survive_a_restart_and_a_user_keeps_one_code(tmp_path):
    path = str(tmp_path / "links.json")
    store = LinkStore(path)
    first = store.create("42", "tamer", "Tai")
    second = store.create("42", "tamer", "Tai")
    assert first not in store.links and store.get(second.lower())["tamer_name"] == "Tai"
    assert LinkStore(path).get(second)["user_id"] == "42"
    assert store.remove_user("42")["tamer_name"] == "Tai"
    assert LinkStore(path).get(second) is None


def test_the_api_links_a_code(client, relay):
    code = relay.links.create("7", "matt", "Matt")
    answer = client.post("/api/v1/discord/link", json={"code": code.lower()})
    assert answer.status_code == 200
    assert answer.json() == {"status": "success", "username": "matt", "tamer_name": "Matt", "user_id": "7"}
    assert client.post("/api/v1/discord/link", json={"code": "ZZZZ"}).status_code == 404
    assert client.post("/api/v1/discord/link", json={}).status_code == 400


def test_a_game_room_is_created_joined_polled_and_carries_messages(client):
    assert client.get("/api/v1/discord/health").json()["status"] == "ok"
    made = client.post("/api/v1/discord/room", json={"host": "Tai", "name": "Tai's Room"}).json()
    room = made["room_id"]
    assert [r["host"] for r in client.get("/api/v1/discord/rooms").json()] == ["Tai"]
    joined = client.post(f"/api/v1/discord/room/{room}/join", json={"player": "Matt"})
    assert joined.json() == {"success": True, "status": "ready"}
    assert client.post(f"/api/v1/discord/room/{room}/join", json={"player": "Izzy"}).status_code == 400
    assert client.post(f"/api/v1/discord/room/{room}/data", json={"type": "host_data", "hp": 3}).json()["success"]
    status = client.get(f"/api/v1/discord/room/{room}/status").json()
    assert status["opponent"] == "Matt" and status["data_queue"][-1]["data"]["hp"] == 3
    assert client.get("/api/v1/discord/room/NOPE/status").status_code == 404


def test_a_room_keeps_the_last_50_messages_and_old_rooms_go():
    rooms = GameRooms()
    room = rooms.create("Tai")
    for n in range(60):
        rooms.add_data(room["id"], n)
    assert [m["data"] for m in rooms.status(room["id"])["data_queue"]] == list(range(10, 60))
    assert rooms.cleanup(datetime.now() + timedelta(minutes=31)) == [room["id"]]


def test_channel_rooms_post_both_sides_once_both_are_in():
    rooms = ChannelRooms()
    assert rooms.host("12a", 1, "Tai", 9) == "Invalid code. Use 6 digits."
    assert rooms.host("123456", 1, "Tai", 9) is None
    assert rooms.join("123456", 2, "Matt") is None
    assert rooms.join("123456", 3, "Izzy") == "Room `123456` is full"
    assert rooms.put_data("123456", {"type": "host_data"}) is None
    room = rooms.put_data("123456", {"type": "guest_data"})
    assert room["host_name"] == "Tai" and room["guest_name"] == "Matt"


def test_the_relay_loads_only_with_a_token():
    """main.py mounts /api/v1/discord and starts the bot only when
    DISCORD_BOT_TOKEN is set; without it nothing imports discord.py."""
    import omninet.main as main
    assert not os.environ.get("DISCORD_BOT_TOKEN")
    paths = {getattr(r, "path", "") for r in main.app.routes}
    assert not any(p.startswith("/api/v1/discord") for p in paths)


def test_the_bot_builds_with_its_commands(relay):
    """discord.py is only needed where a token is set; building the client
    checks the commands without connecting."""
    pytest.importorskip("discord")
    from omninet.discord.bot import create_bot
    bot = create_bot(relay)
    assert {c.name for c in bot.commands} - {"help"} == {      # discord.py adds !help
        "host", "join", "data", "getdata", "status", "link", "unlink", "whoami", "users"}
