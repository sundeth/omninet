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
#:
#: - ``team_size`` forces one team size; ``min_team_size`` /
#:   ``max_team_size`` give a range (both within 1..TEAM_SIZE_LIMIT).
#: - ``rank_prizes``: coins for the 1st, 2nd, ... best teams that fought
#:   (times the season's reward multiplier).
#: - ``day_minutes``: length of an attack "day" counted from the season
#:   start instead of UTC days -- for compressed development seasons.
CONFIG_KEYS = ("attacks_per_day", "charge", "win_score", "loss_score",
               "draw_score", "participation_coins", "team_size",
               "min_team_size", "max_team_size", "rank_prizes", "day_minutes")

#: No arena team fields more Digimon than this (the battle is 3 lanes).
TEAM_SIZE_LIMIT = 3

_INT_KEYS = ("attacks_per_day", "win_score", "loss_score", "draw_score",
             "participation_coins")


def _parse_charge(value):
    if value == "random":
        return "random"
    try:
        return max(0, min(3, int(value)))
    except (TypeError, ValueError):
        return 2


def _team_size(value) -> int:
    return max(1, min(TEAM_SIZE_LIMIT, int(value)))


def default_config() -> dict:
    return {
        "attacks_per_day": settings.max_daily_battles,
        "charge": _parse_charge(settings.arena_default_charge),
        "win_score": settings.arena_win_score,
        "loss_score": settings.arena_loss_score,
        "draw_score": settings.arena_draw_score,
        "participation_coins": settings.arena_participation_coins,
        "min_team_size": _team_size(settings.arena_min_team_size),
        "max_team_size": _team_size(settings.arena_max_team_size),
        "rank_prizes": [settings.arena_first_place_coins,
                        settings.arena_second_place_coins,
                        settings.arena_third_place_coins],
        "day_minutes": None,
    }


def clean_config(config: dict | None) -> dict:
    """Only the known keys, normalised; ``team_size`` becomes a range."""
    cleaned = {k: v for k, v in (config or {}).items() if k in CONFIG_KEYS and v is not None}
    if "charge" in cleaned:
        cleaned["charge"] = _parse_charge(cleaned["charge"])
    for key in _INT_KEYS:
        if key in cleaned:
            cleaned[key] = int(cleaned[key])
    if "team_size" in cleaned:
        size = _team_size(cleaned.pop("team_size"))
        cleaned["min_team_size"] = cleaned["max_team_size"] = size
    for key in ("min_team_size", "max_team_size"):
        if key in cleaned:
            cleaned[key] = _team_size(cleaned[key])
    if "rank_prizes" in cleaned:
        cleaned["rank_prizes"] = [max(0, int(c)) for c in list(cleaned["rank_prizes"])[:100]]
    if "day_minutes" in cleaned:
        cleaned["day_minutes"] = max(1, int(cleaned["day_minutes"]))
    return cleaned


def season_config(season) -> dict:
    """Defaults overlaid with the season's own config.

    The team-size range always holds min <= max: a season that raises only
    the minimum raises the maximum with it.
    """
    config = default_config()
    config.update(clean_config(getattr(season, "config", None)))
    if config["min_team_size"] > config["max_team_size"]:
        own = clean_config(getattr(season, "config", None))
        if "max_team_size" in own:
            config["min_team_size"] = config["max_team_size"]
        else:
            config["max_team_size"] = config["min_team_size"]
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


def attack_day_start(now: datetime, season_start: datetime | None,
                     day_minutes: int | None = None) -> datetime:
    """When today's attack allowance began: UTC midnight, or the season start.

    With *day_minutes* (a compressed development season) the "days" are
    blocks of that many minutes counted from the season start.
    """
    if day_minutes and season_start:
        length = timedelta(minutes=day_minutes)
        if now <= season_start:
            return season_start
        return season_start + ((now - season_start) // length) * length
    midnight = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(midnight, season_start) if season_start else midnight


def next_attack_day(now: datetime, season_start: datetime | None,
                    day_minutes: int | None = None) -> datetime:
    """When the next attack allowance begins (the end of the current day)."""
    start = attack_day_start(now, season_start, day_minutes)
    if day_minutes and season_start:
        return start + timedelta(minutes=day_minutes)
    midnight = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(days=1)
