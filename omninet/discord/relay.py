"""The Discord relay's state, free of discord.py so the HTTP side and its tests
run without it.

Three stores, as the standalone bot kept them:

* ``LinkStore``: pairing codes a player gets from ``!link`` in Discord and
  enters in the game (4 characters), kept in a JSON file under storage/ so a
  restart keeps them.
* ``GameRooms``: the rooms the game creates, joins and polls over HTTP; each
  keeps the last 50 messages the players posted to it.
* ``ChannelRooms``: the rooms of the in-channel commands (``!host`` with a
  6-digit code, ``!join``, battle data posted as embeds).

The standalone bot kept both kinds of room in one dict with two shapes, so
listing the game's rooms raised on a channel room; they are apart here.
"""
from __future__ import annotations

import json
import os
import random
import string
import threading
from datetime import datetime, timedelta

CODE_CHARS = string.ascii_uppercase + string.digits
#: A game room nobody polled for this long is not listed any more.
ROOM_STALE = timedelta(minutes=5)
#: Rooms of either kind are dropped after this long.
ROOM_TTL = timedelta(minutes=30)
#: Messages a game room keeps (and returns per poll).
QUEUE_MAX = 50


class LinkStore:
    """Pairing code -> the Discord user who asked for it."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self.links: dict[str, dict] = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.links, fh, indent=2)
        os.replace(tmp, self.path)

    def create(self, user_id: str, username: str, tamer_name: str) -> str:
        """A new code for *user_id*; an earlier code of theirs is replaced."""
        with self._lock:
            for code in [c for c, d in self.links.items() if d.get("user_id") == str(user_id)]:
                del self.links[code]
            code = "".join(random.choices(CODE_CHARS, k=4))
            while code in self.links:
                code = "".join(random.choices(CODE_CHARS, k=4))
            self.links[code] = {"user_id": str(user_id), "username": username,
                                "tamer_name": tamer_name, "linked_at": datetime.now().isoformat()}
            self._save()
            return code

    def get(self, code: str | None) -> dict | None:
        return self.links.get(str(code or "").strip().upper())

    def find_user(self, user_id) -> tuple[str, dict] | None:
        for code, data in self.links.items():
            if data.get("user_id") == str(user_id):
                return code, data
        return None

    def remove_user(self, user_id) -> dict | None:
        with self._lock:
            found = self.find_user(user_id)
            if not found:
                return None
            del self.links[found[0]]
            self._save()
            return found[1]


class GameRooms:
    """The rooms the game uses over HTTP."""

    def __init__(self):
        self.rooms: dict[str, dict] = {}

    def create(self, host_name: str, name: str = "Battle", user_id=None) -> dict:
        room_id = "".join(random.choices(CODE_CHARS, k=6))
        while room_id in self.rooms:
            room_id = "".join(random.choices(CODE_CHARS, k=6))
        now = datetime.now()
        room = {"id": room_id, "name": name or "Battle", "host_name": host_name, "host_id": user_id,
                "status": "waiting", "created_at": now, "last_active": now,
                "guests": [], "data_queue": []}
        self.rooms[room_id] = room
        return room

    def join(self, room_id: str, player_name: str, user_id=None) -> tuple[int, dict]:
        """(HTTP status, body): one guest makes the room ready."""
        room = self.rooms.get(room_id)
        if room is None:
            return 404, {"error": "Room not found"}
        if room["status"] != "waiting":
            return 400, {"error": "Room already in battle"}
        if any(g["name"] == player_name for g in room["guests"]):
            return 409, {"error": "Name taken"}
        room["guests"].append({"name": player_name, "id": user_id})
        room["last_active"] = datetime.now()
        room["status"] = "ready"
        return 200, {"success": True, "status": room["status"]}

    def status(self, room_id: str) -> dict | None:
        room = self.rooms.get(room_id)
        if room is None:
            return None
        room["last_active"] = datetime.now()
        guests = [g["name"] for g in room["guests"]]
        return {"id": room["id"], "status": room["status"], "host": room["host_name"],
                "guests": guests, "opponent": guests[0] if guests else None,
                "data_queue": room["data_queue"][-QUEUE_MAX:]}

    def add_data(self, room_id: str, data) -> bool:
        room = self.rooms.get(room_id)
        if room is None:
            return False
        room["data_queue"].append({"ts": datetime.now().isoformat(), "data": data})
        del room["data_queue"][:-QUEUE_MAX]
        room["last_active"] = datetime.now()
        return True

    def listing(self, now: datetime | None = None) -> list[dict]:
        now = now or datetime.now()
        return [{"id": code, "room_id": code, "name": room["name"], "host": room["host_name"],
                 "status": room["status"], "created": room["created_at"].isoformat(),
                 "players": [g["name"] for g in room["guests"]] + [room["host_name"]]}
                for code, room in self.rooms.items()
                if now - room["last_active"] < ROOM_STALE]

    def cleanup(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now()
        gone = [code for code, room in self.rooms.items() if now - room["created_at"] > ROOM_TTL]
        for code in gone:
            del self.rooms[code]
        return gone


class ChannelRooms:
    """The rooms of the in-channel commands: a 6-digit code, a host and a guest,
    each side's battle data; when both are in, the bot posts both."""

    def __init__(self):
        self.rooms: dict[str, dict] = {}

    @staticmethod
    def valid_code(code: str | None) -> bool:
        return bool(code) and len(code) == 6 and code.isdigit()

    def ensure(self, code: str, channel_id: int) -> dict:
        return self.rooms.setdefault(code, {
            "host": 0, "host_name": "Host", "host_data": None,
            "guest": 0, "guest_name": "Guest", "guest_data": None,
            "created_at": datetime.now(), "channel_id": channel_id})

    def host(self, code: str, user_id: int, username: str, channel_id: int) -> str | None:
        """None when created, else why not."""
        if not self.valid_code(code):
            return "Invalid code. Use 6 digits."
        if code in self.rooms:
            return f"Room `{code}` already exists"
        room = self.ensure(code, channel_id)
        room.update(host=user_id, host_name=username, guest=None, guest_name=None)
        return None

    def join(self, code: str, user_id: int, username: str) -> str | None:
        if not self.valid_code(code):
            return "Invalid code"
        room = self.rooms.get(code)
        if room is None:
            return f"Room `{code}` not found"
        if room["guest"]:
            return f"Room `{code}` is full"
        room.update(guest=user_id, guest_name=username)
        return None

    def put_data(self, code: str, battle_data: dict) -> dict | None:
        """Store a side's data; the room when both sides are in, else None."""
        room = self.rooms.get(code)
        kind = battle_data.get("type") if isinstance(battle_data, dict) else None
        if room is None or kind not in ("host_data", "guest_data"):
            return None
        room[kind] = battle_data
        return room if room["host_data"] and room["guest_data"] else None

    def cleanup(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now()
        gone = [code for code, room in self.rooms.items() if now - room["created_at"] > ROOM_TTL]
        for code in gone:
            del self.rooms[code]
        return gone


class Relay:
    """The three stores, one per process."""

    def __init__(self, storage_path: str):
        self.links = LinkStore(os.path.join(storage_path, "linked_users.json"))
        self.game_rooms = GameRooms()
        self.channel_rooms = ChannelRooms()
        #: Set by the bot once it is logged in to Discord.
        self.bot_ready = False


_relay: Relay | None = None


def get_relay() -> Relay:
    from omninet.config import settings
    global _relay
    if _relay is None:
        _relay = Relay(settings.discord_storage_path)
    return _relay
