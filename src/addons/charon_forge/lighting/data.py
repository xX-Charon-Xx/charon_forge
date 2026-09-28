"""The game's lighting data: resources/lighting/lighting.json and its textures.

Written by the extraction pipeline (pipeline/outputs/lighting.py) from the
game's sky tables - nothing in it is tuned by hand:

    globals.sky         gcskyglobals: day / dusk / night / space light colours,
                        the sunset and night fade thresholds, the ambient factor
    globals.planet_sky  the planet sun disc
    globals.graphics    gcgraphicsglobals: tonemap exposure, model renderer light
    planet.<list>       day / dusk / night / day_firestorm / day_gravstorm sky
                        entries, generic ('Generic', 'Dark') and per biome
    space.common/rare   spaceskycolours / spacerareskycolours entries
    spacedome           the space nebula masks (R, G, B are separate masks)
    nebulaplasma        the tiling nebula wisps (filaments in alpha)

Loaded on first use and cached.
"""

import json
import os

ADDON_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
LIGHTING_PATH = os.path.join(ADDON_PATH, "resources", "lighting")
LIGHTING_JSON = os.path.join(LIGHTING_PATH, "lighting.json")
_data = None


def load():
    global _data
    if _data is None:
        try:
            with open(LIGHTING_JSON, encoding="utf-8") as f:
                _data = json.load(f)
        except (OSError, ValueError) as exc:
            print("Charon Forge: no lighting data (%r)" % exc)
            _data = {}
    return _data


def available():
    return bool(load())


def sky_globals():
    return load().get("globals", {}).get("sky", {})


def planet_lists(kind):
    """{list name: [entries]} for 'day', 'dusk', 'night', 'day_firestorm' ..."""
    return load().get("planet", {}).get(kind, {})


def planet_entry(kind, list_name, index, fallback="Generic"):
    """An entry of a planet sky list; a biome with no list of its own uses the
    generic one, the way the game does."""
    lists = planet_lists(kind)
    entries = lists.get(list_name) or lists.get(fallback) or []
    if not entries:
        return {}
    return entries[index % len(entries)]


def planet_list_names():
    """The day lists that exist: 'Generic' first, then the biomes that have
    their own."""
    names = [n for n in planet_lists("day") if n not in ("Generic", "Dark")]
    return ["Generic"] + sorted(names)


def space_entries(kind):
    return load().get("space", {}).get(kind, [])


def space_entry(kind, index):
    entries = space_entries(kind)
    return entries[index % len(entries)] if entries else {}


_space_keys = None


def space_sky_keys():
    """Every space sky as (key, kind, index, star colour): 'c3' is common
    entry 3, 'r12' rare entry 12. Built once - the panel asks on every redraw."""
    global _space_keys
    if _space_keys is None:
        _space_keys = [(prefix + str(i), kind, i, entry.get("GalaxyStarType") or "?")
                       for kind, prefix in (("common", "c"), ("rare", "r"))
                       for i, entry in enumerate(space_entries(kind))]
    return _space_keys


def space_entry_by_key(key):
    kind = "rare" if key.startswith("r") else "common"
    try:
        return space_entry(kind, int(key[1:]))
    except ValueError:
        return space_entry("common", 0)


def _texture(name_key):
    name = load().get(name_key)
    return os.path.join(LIGHTING_PATH, name) if name else None


def spacedome_path():
    return _texture("spacedome")


def nebulaplasma_path():
    return _texture("nebulaplasma")


# Colour ---
def to_linear(rgb):
    """The tables hold display (sRGB) values, like any colour picked by eye;
    Blender's lights and shaders take linear ones."""
    def channel(c):
        c = max(0.0, float(c))
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return tuple(channel(c) for c in (list(rgb) + [0.0, 0.0, 0.0])[:3])


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def scale(rgb, s):
    return tuple(c * s for c in rgb)
