"""The game's own colour and finish data for every high res part.

Read from resources/colours.json, which the extraction pipeline writes from
the game files (BASEBUILDINGOBJECTSTABLE and the palette and material
tables). Nothing in it is tuned by hand.

    palettes       every palette, indexed by the number UserData stores
    palette_groups which palettes a part may use (ColourPaletteGroupId)
    finishes       every finish, with the index UserData stores
    finish_groups  which finishes a part may use (MaterialGroupId)
    objects        per part: its palette and finish groups and defaults, and
                   the LIGHT nodes of its scenes (how bright its lamps are)

UserData, as the game packs it:

    palette index = UserData & 0xFFFFFF       (bits 8, 16, 17 are not colour)
    finish index  = (UserData >> 24) & 0xFF   the finish's own index, which is
                                              also the texture slice it shows

Loaded on first use and cached; an edit to the file on disk is picked up.
"""

import json
import os

from . import paths

_data = None
_stamp = None


def _load():
    global _data, _stamp
    try:
        info = os.stat(paths.COLOURS_JSON)
        stamp = (info.st_mtime, info.st_size)
    except OSError:
        stamp = None
    if _data is not None and stamp == _stamp:
        return _data
    _stamp = stamp

    try:
        with open(paths.COLOURS_JSON, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (IOError, OSError, ValueError):
        # a missing or half written file keeps whatever was loaded before
        _data = _data or {"palettes": {}, "palette_ids": {}, "palette_groups": {},
                          "finishes": {}, "finish_groups": {}, "objects": {}}
        return _data

    palettes = {int(p["index"]): p for p in raw.get("palettes", [])}
    _data = {
        "palettes": palettes,
        "palette_ids": {p["id"]: p for p in palettes.values()},
        "palette_groups": raw.get("palette_groups", {}),
        "finishes": raw.get("finishes", {}),
        "finish_groups": raw.get("finish_groups", {}),
        "objects": raw.get("objects", {}),
    }
    return _data


def reload():
    global _data
    _data = None
    return _load()


# Palettes ---
def palette(index):
    """{id, label, p, s, t, q, ...} for a palette index, or None."""
    try:
        return _load()["palettes"].get(int(index))
    except (TypeError, ValueError):
        return None


def palette_by_id(palette_id):
    return _load()["palette_ids"].get(palette_id)


def palette_label(entry):
    """What the game calls a palette, falling back to its table id."""
    if not entry:
        return ""
    return entry.get("label") or entry.get("name_en") or entry.get("id", "")


def group_palettes(group):
    """The palettes of a palette group, in the order the game lists them."""
    data = _load()
    out = []
    for palette_id in data["palette_groups"].get(group or "", []):
        entry = data["palette_ids"].get(palette_id)
        if entry is not None:
            out.append(entry)
    return out


# Objects ---
def object_info(object_id):
    """The colours.json record for a part id; {} when it has none."""
    if not object_id:
        return {}
    return _load()["objects"].get(object_id.replace("^", ""), {})


def palette_groups_of(object_id):
    """(group, station group) - the second only when a space station gives
    the part a different set, else None. (None, None) when the game does not
    let the part be recoloured at all."""
    info = object_info(object_id)
    return info.get("palette_group"), info.get("station_palette_group")


def is_recolourable(object_id):
    return bool(object_info(object_id).get("palette_group"))


def allowed_palettes(object_id):
    """Every palette index the game offers this part, either group."""
    group, station = palette_groups_of(object_id)
    return {p["index"] for g in (group, station) if g for p in group_palettes(g)}


def default_palette_index(object_id):
    """The palette a freshly placed part has. 0 when the game names none."""
    info = object_info(object_id)
    index = info.get("default_palette_index")
    if index is None:
        entry = palette_by_id(info.get("default_palette") or "")
        index = entry["index"] if entry else 0
    return int(index)


# Finishes ---
def finishes_of(object_id):
    """[(finish index, finish id, entry)] a part may use, in menu order.

    The index is the finish's own - the number a save stores - not its
    position in the group: the RUSTED group holds only MAT_RUSTED, which is
    still finish 1.
    """
    data = _load()
    group = object_info(object_id).get("finish_group")
    out = []
    for finish_id in data["finish_groups"].get(group or "", {}).get("finishes", []):
        entry = data["finishes"].get(finish_id)
        if entry is not None:
            out.append((int(entry["index"]), finish_id, entry))
    return out


def can_change_finish(object_id):
    info = object_info(object_id)
    return bool(info.get("can_change_finish")) and bool(finishes_of(object_id))


def finish_entry(object_id, finish_index):
    """(finish id, entry) for a part's finish index, or (None, None)."""
    for index, finish_id, entry in finishes_of(object_id):
        if index == int(finish_index):
            return finish_id, entry
    return None, None


def finish_label(object_id, finish_index):
    finish_id, entry = finish_entry(object_id, finish_index)
    if entry is None:
        return ""
    return entry.get("name_en") or finish_id


def default_finish_index(object_id):
    return int(object_info(object_id).get("default_finish_index") or 0)


def default_user_data(object_id):
    """The UserData a part has when first placed in game."""
    return (default_finish_index(object_id) << 24) | default_palette_index(object_id)


# Light ---
def light_power(object_id):
    """Watts the part's own game lights put out: each LIGHT node reaches
    `intensity / d^2`, which a Blender emitter matches at 4 pi x intensity.
    Lights inside effect scenes (beams, sparks) are left out."""
    total = 0.0
    for light in object_info(object_id).get("lights") or []:
        if light.get("in_effect"):
            continue
        total += 12.566370614359172 * float(light.get("intensity", 0.0))
    return total
