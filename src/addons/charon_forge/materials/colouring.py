"""Colouring high res parts: colour and finish are object properties read by
shared materials, so never copy a mesh or material to recolour."""

import json

import bpy

from . import game_data, station_paint
from .finish_nodes import strip_legacy_finish_props
from .properties import (COLOURISE_GROUP, LEGACY_FINISH_PROPS, MESH_TAG,
                         PROP_FINISH, PROP_READONLY_COLOUR,
                         PROP_READONLY_MATERIAL, PROP_USER_DATA, SLOT_ORDER,
                         SLOT_PROPS)

# UserData layout: palette in the low 24 bits, finish in the top 8; bits 8, 16
# and 17 aren't colour and must survive a recolour
COLOUR_BITS = 0xFFFFFF
RESERVED_BITS = (1 << 8) | (1 << 16) | (1 << 17)
COLOUR_MASK = COLOUR_BITS & ~RESERVED_BITS
FINISH_SHIFT = 24
FINISH_MASK = 0xFF << FINISH_SHIFT


# UserData ---
def to_int(user_data_value):
    try:
        return int(user_data_value)
    except (TypeError, ValueError):
        return None


def decode(user_data_value):
    """(palette index, finish index), or None if it is not a number."""
    value = to_int(user_data_value)
    if value is None:
        return None
    return value & COLOUR_MASK, (value & FINISH_MASK) >> FINISH_SHIFT


def encode(base_value, palette_index=None, finish_index=None):
    """`base_value` with the palette and/or finish replaced, every other bit
    kept."""
    value = to_int(base_value) or 0
    if palette_index is not None:
        value = (value & ~COLOUR_MASK) | (int(palette_index) & COLOUR_MASK)
    if finish_index is not None:
        value = (value & ~FINISH_MASK) | ((int(finish_index) << FINISH_SHIFT) & FINISH_MASK)
    return value


# Telling the systems apart ---
def is_high_res(bpy_object):
    """True when the object's mesh came out of the high res library - the test
    the flat material code uses before it paints anything over a part."""
    data = getattr(bpy_object, "data", None)
    return data is not None and MESH_TAG in data


def object_id_of(bpy_object):
    """The library id a part's mesh came from, else its ObjectID, else None.
    A merged group has neither."""
    data = getattr(bpy_object, "data", None)
    if data is not None and MESH_TAG in data:
        return data[MESH_TAG]
    raw = bpy_object.get("ObjectID")
    return raw.replace("^", "") if isinstance(raw, str) else None


def is_colourable(bpy_object):
    """True if any of its materials carries the colourise node group, or has
    painted hull tiles (station_paint.py)."""
    if station_paint.is_painted(bpy_object):
        return True
    for slot in bpy_object.material_slots:
        material_data = slot.material
        if material_data is None or material_data.node_tree is None:
            continue
        for node in material_data.node_tree.nodes:
            if node.type == "GROUP" and node.node_tree is not None \
                    and node.node_tree.name.startswith(COLOURISE_GROUP):
                return True
    return False


# Resolving ---
def resolve(object_id, user_data_value):
    """(palette, finish index, colour label, finish label) for this UserData,
    or None when the game has no such palette."""
    indices = decode(user_data_value)
    if indices is None:
        return None
    palette_index, finish_index = indices
    palette = game_data.palette(palette_index)
    if palette is None:
        return None
    finish = game_data.finish_label(object_id, finish_index) if object_id else ""
    return palette, finish_index, game_data.palette_label(palette), finish


# Applying ---
def apply_palette(bpy_object, palette, finish_index=0):
    """Write the four palette colours and the finish onto an object."""
    for prop_name, slot in zip(SLOT_PROPS, SLOT_ORDER):
        bpy_object[prop_name] = tuple(palette[slot])
    bpy_object[PROP_FINISH] = int(finish_index)
    station_paint.show_paint_layers(bpy_object)
    # left over from the old hand-tuned finish preview
    for prop in LEGACY_FINISH_PROPS:
        if prop in bpy_object:
            del bpy_object[prop]
    # the primary colour, for Solid shading set to Object colour
    bpy_object.color = tuple(palette["p"])
    show_object_colour()


def _write_labels(bpy_object, colour_label, finish_label):
    bpy_object[PROP_READONLY_COLOUR] = colour_label or ""
    bpy_object[PROP_READONLY_MATERIAL] = finish_label or ""


def apply(bpy_object, user_data_value, tag=True):
    """Colour one object from a UserData value, without writing its UserData.
    Returns the palette applied, or None."""
    resolved = resolve(object_id_of(bpy_object), user_data_value)
    if resolved is None:
        return None
    palette, finish_index, colour_label, finish_label = resolved
    apply_palette(bpy_object, palette, finish_index)
    _write_labels(bpy_object, colour_label, finish_label)
    if tag:
        bpy_object.update_tag()
    return palette


def apply_many(pairs, tag=False, update=False, fresh=False):
    """Colour many (object, UserData) pairs, resolving each distinct pair once.
    Returns (number coloured, number unresolved)."""
    cache = {}
    applied = unresolved = 0
    slots = tuple(zip(SLOT_PROPS, SLOT_ORDER))
    for bpy_object, user_data_value in pairs:
        key = (object_id_of(bpy_object), str(user_data_value))
        values = cache.get(key)
        if values is None and key not in cache:
            resolved = resolve(key[0], user_data_value)
            if resolved is not None:
                palette, finish_index, colour_label, finish_label = resolved
                values = (
                    tuple((prop, tuple(palette[slot])) for prop, slot in slots),
                    int(finish_index),
                    tuple(palette["p"]),
                    colour_label or "",
                    finish_label or "",
                )
            cache[key] = values
        if values is None:
            unresolved += 1
            continue
        slot_values, finish_index, colour, colour_label, finish_label = values
        for prop, value in slot_values:
            bpy_object[prop] = value
        bpy_object[PROP_FINISH] = finish_index
        station_paint.show_paint_layers(bpy_object)
        if not fresh:
            for prop in LEGACY_FINISH_PROPS:
                if prop in bpy_object:
                    del bpy_object[prop]
        bpy_object.color = colour
        bpy_object[PROP_READONLY_COLOUR] = colour_label
        bpy_object[PROP_READONLY_MATERIAL] = finish_label
        if tag:
            bpy_object.update_tag()
        applied += 1
    if applied:
        show_object_colour()
    if update:
        bpy.context.view_layer.update()
    return applied, unresolved


# A group's parts, as the group code caches them - see objects/group.py. Named
# here rather than imported: the group module imports this package.
GROUP_ID_PROP = "GroupID"
GROUP_CHILD_CACHE_PROP = "child_cache"


def sync_group_children(bpy_object):
    """Write a group's UserData into every part in its cache.
    Returns how many parts were updated."""
    if GROUP_ID_PROP not in bpy_object or GROUP_CHILD_CACHE_PROP not in bpy_object:
        return 0
    master = bpy_object.get(PROP_USER_DATA)
    if master is None:
        return 0
    try:
        children = json.loads(bpy_object[GROUP_CHILD_CACHE_PROP])
    except (TypeError, ValueError):
        return 0
    if not isinstance(children, dict):
        return 0

    for cache_data in children.values():
        if isinstance(cache_data, dict):
            cache_data[PROP_USER_DATA] = master
    bpy_object[GROUP_CHILD_CACHE_PROP] = json.dumps(children)
    return len(children)


def recolour(objects, colour_index=None, material_index=None, tag=True):
    """Set a palette and/or finish on objects, writing it into their UserData.
    Returns (number coloured, number unresolved)."""
    pairs = []
    for bpy_object in objects:
        value = encode(bpy_object.get(PROP_USER_DATA, 0), colour_index, material_index)
        bpy_object[PROP_USER_DATA] = str(value)
        sync_group_children(bpy_object)
        pairs.append((bpy_object, value))
    return apply_many(pairs, tag=tag)


def recolour_from_user_data(objects, user_data_value, tag=True):
    """Set objects to an exact UserData value; one that doesn't resolve leaves
    them untouched. Returns (number coloured, number unresolved)."""
    objects = list(objects)
    if decode(user_data_value) is None:
        return 0, len(objects)
    value = str(int(user_data_value))
    done = failed = 0
    for bpy_object in objects:
        if apply(bpy_object, value, tag=tag) is None:
            failed += 1
            continue
        bpy_object[PROP_USER_DATA] = value
        sync_group_children(bpy_object)
        done += 1
    return done, failed


def default_user_data(object_id):
    """The UserData the game gives a freshly placed part."""
    return game_data.default_user_data(object_id)


def clear(bpy_object):
    """Strip the colour properties, returning an object to its raw textures."""
    for prop in SLOT_PROPS + (PROP_FINISH,):
        if prop in bpy_object:
            del bpy_object[prop]
    strip_legacy_finish_props([bpy_object])
    bpy_object.update_tag()


# Viewport ---
def show_object_colour():
    """Switch Solid views on Material colour to Object colour, so parts show
    their colour. Returns how many viewports changed."""
    return use_object_colour_in_viewport(only_from="MATERIAL")


def use_object_colour_in_viewport(enable=True, only_solid=True, only_from=None):
    """Point Solid viewport shading at the per object colour; `only_from` limits
    it to views on that colour type. Returns how many viewports changed."""
    colour_type = "OBJECT" if enable else "MATERIAL"
    changed = 0
    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return 0
    for window in window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type != "VIEW_3D":
                    continue
                shading = space.shading
                if only_solid and shading.type != "SOLID":
                    continue
                if only_from is not None and shading.color_type != only_from:
                    continue
                if shading.color_type != colour_type:
                    shading.color_type = colour_type
                    changed += 1
    return changed
