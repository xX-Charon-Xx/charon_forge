"""User lighting presets: every setting of scene.charon_lighting, as JSON in
~/CharonForge/lighting_presets/<name>.json, usable in any scene.

Neither `enabled` nor the lamps are saved: loading a preset never turns the
rig or the game lamps on or off - the lamps are only ever turned on by the
Lamps button.
"""

import json
import os
import re

PRESET_DIR = os.path.join(os.path.expanduser("~"), "CharonForge", "lighting_presets")

KEYS = (
    "context", "station_type", "planet_list", "weather", "planet_sky",
    "dark_night", "time_of_day", "star_filter", "space_sky", "space_style",
    "nebula_shape", "nebula", "sun_heading", "sun_height", "brightness",
    "sunlight", "glow", "ambient", "sky_brightness", "sun_size",
    "sun_glow", "sun_halo", "stars", "clouds", "night_light", "noon_height",
)
# set first, so the sky numbers that depend on them are valid when set
LIST_KEYS = ("context", "station_type", "planet_list", "weather", "star_filter")


def names():
    if not os.path.isdir(PRESET_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(PRESET_DIR) if f.endswith(".json"))


def path_of(name):
    safe = re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "Preset"
    return os.path.join(PRESET_DIR, safe + ".json")


def save(settings, name):
    """Returns the preset's name as it is stored (unsafe characters replaced)."""
    os.makedirs(PRESET_DIR, exist_ok=True)
    path = path_of(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({key: getattr(settings, key) for key in KEYS}, f, indent=1)
    return os.path.basename(path)[:-5]


def read(name):
    with open(path_of(name), encoding="utf-8") as f:
        values = json.load(f)
    ordered = [k for k in LIST_KEYS if k in values] + \
              [k for k in KEYS if k in values and k not in LIST_KEYS]
    return [(key, values[key]) for key in ordered]


def delete(name):
    path = path_of(name)
    if os.path.exists(path):
        os.remove(path)
