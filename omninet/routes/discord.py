"""The Discord relay's HTTP API, as the game calls it (/api/v1/discord/...).

Mounted only when ``DISCORD_BOT_TOKEN`` is set (main.py). The paths and
answers are the standalone bot's (port 5000 there), so the game's client
keeps its shape:

    GET  /health                 {"status": "ok", "bot": "connected" | "connecting"}
    POST /link        {code}     the Discord user behind a pairing code (404 if none)
    GET  /rooms                  the game rooms polled in the last 5 minutes
    POST /room        {host, name, user_id}       a new room: {success, room_id, room_code}
    POST /room/{id}/join   {player, user_id}      one guest makes it ready
    GET  /room/{id}/status       status, guests and the last 50 messages
    POST /room/{id}/data   {...}  a message for the other side
"""
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from omninet.discord.relay import get_relay

router = APIRouter(prefix="/discord", tags=["Discord"])


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


@router.get("/health")
async def health():
    return {"status": "ok", "bot": "connected" if get_relay().bot_ready else "connecting"}


@router.post("/link")
async def link(data: dict[str, Any] = Body(default_factory=dict)):
    code = data.get("code")
    if not code:
        return _error(400, "Missing code")
    user = get_relay().links.get(code)
    if user is None:
        return _error(404, "Invalid code or not linked yet")
    return {"status": "success", "username": user["username"], "tamer_name": user["tamer_name"],
            "user_id": user["user_id"]}


@router.get("/rooms")
async def rooms():
    return get_relay().game_rooms.listing()


@router.post("/room")
async def create_room(data: dict[str, Any] = Body(default_factory=dict)):
    host = data.get("host")
    if not host:
        return _error(400, "Missing host name")
    room = get_relay().game_rooms.create(host, data.get("name") or "Battle", data.get("user_id"))
    return {"success": True, "room_id": room["id"], "room_code": room["id"]}


@router.post("/room/{room_id}/join")
async def join_room(room_id: str, data: dict[str, Any] = Body(default_factory=dict)):
    status, body = get_relay().game_rooms.join(room_id, data.get("player"), data.get("user_id"))
    return JSONResponse(body, status_code=status)


@router.get("/room/{room_id}/status")
async def room_status(room_id: str):
    status = get_relay().game_rooms.status(room_id)
    return status if status is not None else _error(404, "Room not found")


@router.post("/room/{room_id}/data")
async def room_data(room_id: str, data: Any = Body(default=None)):
    if not get_relay().game_rooms.add_data(room_id, data):
        return _error(404, "Room not found")
    return {"success": True}
