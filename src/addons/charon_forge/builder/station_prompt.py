"""Offering a base's own space station when a space station base comes in.

A PlayerSpaceStationBase is built inside a system's station, and its
GalacticAddress says which system. When the base builder addon hands us one
to build (HighResBuilderMixin.deserialise_from_data), the address is checked
and, if it gives a station, the Forge's station popup opens on its Galactic
Address tab with the address filled in - so the base can be built in the
station it belongs to.
"""

import bpy

# the base type the game gives a base in a space station - see
# save_editor/save_editor_utils.BaseType.SPACESTATION_BASE
SPACESTATION_BASE = "PlayerSpaceStationBase"

# the popup opens this long after the import, once the base is in
_DELAY = 0.2


def base_type_of(data):
    base_type = (data or {}).get("BaseType")
    if isinstance(base_type, dict):
        return base_type.get("PersistentBaseTypes")
    return base_type


def station_address(data):
    """The base's galactic address, as text, if it is a space station base
    whose address gives a station - else None."""
    if base_type_of(data) != SPACESTATION_BASE:
        return None
    address = data.get("GalacticAddress")
    if address in (None, "", 0):
        return None
    # a save's address is a number, often kept as decimal text - written as
    # hex so it can't be taken for 12 portal glyphs
    text = address.strip() if isinstance(address, str) else "0x%X" % int(address)
    if text.isdigit():
        text = "0x%X" % int(text)
    from ..utils import seed_utils
    try:
        seed_utils.station_config(seed_utils.parse_address(text))
    except (ValueError, KeyError, StopIteration, OSError, TypeError):
        return None
    return text


def stored_address(scene):
    """The galactic address of the base the base builder addon holds in the
    scene (scene.nms_base_tool, filled on import) - if it is a space station
    base whose address gives a station - else None."""
    tool = getattr(scene, "nms_base_tool", None)
    if tool is None:
        return None
    return station_address({
        "BaseType": {"PersistentBaseTypes": getattr(tool, "string_base_type", "")},
        "GalacticAddress": getattr(tool, "string_address", ""),
    })


def offer_station(data):
    """After a space station base is imported, open the station popup with
    its address. Nothing happens for any other base, or an address that
    gives no station."""
    text = station_address(data)
    if text is None:
        return
    bpy.app.timers.register(lambda: _open_popup(text), first_interval=_DELAY)


def _open_popup(text):
    """Open the popup in a 3D viewport - a timer has no window of its own."""
    window_manager = bpy.context.window_manager
    for window in window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is None:
                continue
            with bpy.context.temp_override(window=window, area=area, region=region):
                bpy.ops.object.charon_forge_edit_station(
                    "INVOKE_DEFAULT", mode="ADDRESS", address=text, from_base=True
                )
            return None
    return None
