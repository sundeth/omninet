"""
Background pictures on disk, for the shop's background cosmetics and Specials.

A background is named by its base file name (``sprite_name``, e.g. ``bg_sky``
or ``bg_premium_swamp``) and lives in ``<shop_assets_base>/backgrounds/`` as
up to eight files, the game's own layout (Omnipet ui/windows/window_background):

    <base>.png            <base>_high.png                one fixed picture
    <base>_day.png        <base>_day_high.png            by time of day:
    <base>_dusk.png       <base>_dusk_high.png           06-16 day, 16-19 dusk,
    <base>_night.png      <base>_night_high.png          19-06 night

The ``_high`` files are the high-resolution versions (1024x1024); the others
are the game's 96x96.
"""
import base64
import os
from pathlib import Path

from omninet.config import settings

TIMES_OF_DAY = ("day", "dusk", "night")


def background_dir() -> Path:
    return Path(settings.shop_assets_base) / "backgrounds"


def background_base(sprite_name: str | None) -> str:
    """The base file name: no folder, no ``.png``."""
    name = os.path.basename(sprite_name or "")
    return name[:-4] if name.lower().endswith(".png") else name


def background_variant_names(sprite_name: str | None) -> list[str]:
    """Every file name a background may have, best first."""
    base = background_base(sprite_name)
    if not base:
        return []
    names = []
    for time in TIMES_OF_DAY:
        names.append(f"{base}_{time}.png")
        names.append(f"{base}_{time}_high.png")
    names.append(f"{base}.png")
    names.append(f"{base}_high.png")
    return names


def background_files(sprite_name: str | None) -> dict[str, Path]:
    """The files of a background that exist on disk: {file name: path}."""
    folder = background_dir()
    out = {}
    for name in background_variant_names(sprite_name):
        path = folder / name
        if path.is_file():
            out[name] = path
    return out


def background_flags(sprite_name: str | None) -> tuple[bool, bool]:
    """(day_night, high_res) as the files on disk have them: day/night needs
    both a ``_day`` and a ``_night`` picture; high-res any ``_high`` one."""
    files = background_files(sprite_name)
    base = background_base(sprite_name)
    day_night = f"{base}_day.png" in files and f"{base}_night.png" in files
    high_res = any(name.endswith("_high.png") for name in files)
    return day_night, high_res


def background_payload(sprite_name: str | None) -> dict[str, str]:
    """Every picture of a background, base64, for a download."""
    out = {}
    for name, path in background_files(sprite_name).items():
        out[name] = base64.b64encode(path.read_bytes()).decode("ascii")
    return out


def background_preview_paths(sprite_name: str | None, small: bool = False) -> list[Path]:
    """The day picture first for a preview: high-resolution first, or with
    *small* the game's 96x96 first (a list of thumbnails stays light)."""
    base = background_base(sprite_name)
    if not base:
        return []
    order = []
    for time in ("day", None, "dusk", "night"):
        stem = f"{base}_{time}" if time else base
        pair = [f"{stem}.png", f"{stem}_high.png"] if small else [f"{stem}_high.png", f"{stem}.png"]
        order.extend(pair)
    folder = background_dir()
    return [folder / name for name in order]
