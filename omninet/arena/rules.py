"""
A season's effective settings.

Server defaults come from ``settings``; a season's ``config`` JSON overrides
any of them for that season (an admin season, a development season, or the
forced ``arena_season_config`` on automatic seasons).
"""
import json
from datetime import UTC, datetime, timedelta

from omninet.config import settings

#: Keys a season config may set.
CONFIG_KEYS = ("attacks_per_day", "charge", "win_score", "loss_score",
               "draw_score", "participation_coins")


def _parse_charge(value):
    if value == "random":
        return "random"
    try:
        return max(0, min(3, int(value)))
    except (TypeError, ValueError):
        return 2


def default_config() -> dict:
    return {
        "attacks_per_day": settings.max_daily_battles,
        "charge": _parse_charge(settings.arena_default_charge),
        "win_score": settings.arena_win_score,
        "loss_score": settings.arena_loss_score,
        "draw_score": settings.arena_draw_score,
        "participation_coins": settings.arena_participation_coins,
    }


def clean_config(config: dict | None) -> dict:
    """Only the known keys, with charge normalised."""
    cleaned = {k: v for k, v in (config or {}).items() if k in CONFIG_KEYS and v is not None}
    if "charge" in cleaned:
        cleaned["charge"] = _parse_charge(cleaned["charge"])
    for key in ("attacks_per_day", "win_score", "loss_score", "draw_score",
                "participation_coins"):
        if key in cleaned:
            cleaned[key] = int(cleaned[key])
    return cleaned


def season_config(season) -> dict:
    """Defaults overlaid with the season's own config."""
    config = default_config()
    config.update(clean_config(getattr(season, "config", None)))
    return config


def _json_setting(raw: str) -> dict:
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def forced_restrictions() -> dict:
    """``arena_season_restrictions`` as a dict (automatic seasons)."""
    return _json_setting(settings.arena_season_restrictions)


def forced_config() -> dict:
    """``arena_season_config`` as a dict (automatic seasons)."""
    return clean_config(_json_setting(settings.arena_season_config))


def season_anchor() -> datetime:
    anchor = datetime.fromisoformat(settings.arena_season_anchor.replace("Z", "+00:00"))
    return anchor if anchor.tzinfo else anchor.replace(tzinfo=UTC)


def season_length() -> timedelta:
    return timedelta(hours=max(1 / 60, float(settings.arena_season_length_hours)))


def auto_slot(now: datetime, anchor: datetime | None = None,
              length: timedelta | None = None) -> tuple[datetime, datetime]:
    """The scheduled slot [start, end) that contains *now*."""
    anchor = anchor or season_anchor()
    length = length or season_length()
    count = (now - anchor) // length
    start = anchor + count * length
    return start, start + length


def auto_season_name(slot_start: datetime, starts_at: datetime, length: timedelta) -> str:
    """Weekly seasons are named for their week; shorter ones for their start."""
    if length == timedelta(days=7):
        return f"Week of {slot_start:%B %d, %Y}"
    return f"Season {starts_at:%b %d %H:%M} UTC"


def attack_day_start(now: datetime, season_start: datetime | None) -> datetime:
    """When today's attack allowance began: UTC midnight, or the season start."""
    midnight = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(midnight, season_start) if season_start else midnight
