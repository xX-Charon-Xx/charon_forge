"""Colouring parts from the high res library, the way the game does it.

Every colourable material in the library carries an "NMS_Colourise" node group
whose four palette slots are Attribute nodes of type OBJECT, reading the
object properties nms_p / nms_s / nms_t / nms_q. Every finish-capable material
holds all of its finish texture slices behind a switch reading the object
property nms_finish. So both the colour and the finish live on the OBJECT:
recolouring a part is five property writes, no material is touched, and a
thousand placements of a part share ONE mesh and ONE set of materials while
each shows its own colour and finish. Never copy a mesh or a material to
recolour something.

What the properties are set to comes only from the game's data (game_data.py,
resources/colours.json):

    UserData & 0xFFFFFF       palette index -> the palette's four colours
    (UserData >> 24) & 0xFF   finish index  -> nms_finish, the texture slice

Any palette can go on any part, and any finish index on any part: the game's
menus only offer a part its own palette and finish groups, but Charon Forge
lets you use them all. A finish index the part's textures have no slice for
shows its last slice.
"""

import bpy

from . import game_data
from .finish_nodes import strip_legacy_finish_props
from .properties import (COLOURISE_GROUP, LEGACY_FINISH_PROPS, MESH_TAG,
                         PROP_FINISH, PROP_READONLY_COLOUR,
                         PROP_READONLY_MATERIAL, PROP_USER_DATA, SLOT_ORDER,
                         SLOT_PROPS)

# UserData layout - the game's, and the same one the base builder addon's
# utils/userdata.py preserves: bits 8, 16 and 17 sit inside the colour range
# but are not colour, and must survive a recolour.
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
    """True if any of its materials carries the colourise node group."""
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
    """What a part with this UserData shows in game.

    Returns:
        tuple: (palette entry, finish index, colour label, finish label), or
            None when the palette index is not one the game defines - the
            part is then left untouched rather than painted with nothing.
    """
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
    # left over from the old hand-tuned finish preview
    for prop in LEGACY_FINISH_PROPS:
        if prop in bpy_object:
            del bpy_object[prop]
    # Solid shading set to Object colour draws this: the materials are shared,
    # so only the object can carry a per part viewport colour. Primary is the
    # body colour, the one that reads as "what colour is this part".
    bpy_object.color = tuple(palette["p"])


def _write_labels(bpy_object, colour_label, finish_label):
    bpy_object[PROP_READONLY_COLOUR] = colour_label or ""
    bpy_object[PROP_READONLY_MATERIAL] = finish_label or ""


def apply(bpy_object, user_data_value, tag=True):
    """Colour one object from a UserData value. Its UserData is not written.

    Returns:
        dict: The palette applied, or None (object untouched).
    """
    resolved = resolve(object_id_of(bpy_object), user_data_value)
    if resolved is None:
        return None
    palette, finish_index, colour_label, finish_label = resolved
    apply_palette(bpy_object, palette, finish_index)
    _write_labels(bpy_object, colour_label, finish_label)
    if tag:
        bpy_object.update_tag()
    return palette


def apply_many(pairs, tag=False, update=False):
    """Colour many (object, UserData) pairs, resolving each distinct
    (part id, UserData) once.

    Returns:
        tuple: (number coloured, number whose UserData did not resolve)
    """
    cache = {}
    applied = unresolved = 0
    for bpy_object, user_data_value in pairs:
        key = (object_id_of(bpy_object), str(user_data_value))
        if key not in cache:
            cache[key] = resolve(key[0], user_data_value)
        resolved = cache[key]
        if resolved is None:
            unresolved += 1
            continue
        palette, finish_index, colour_label, finish_label = resolved
        apply_palette(bpy_object, palette, finish_index)
        _write_labels(bpy_object, colour_label, finish_label)
        if tag:
            bpy_object.update_tag()
        applied += 1
    if update:
        bpy.context.view_layer.update()
    return applied, unresolved


def recolour(objects, colour_index=None, material_index=None, tag=True):
    """Set a palette and/or finish on objects, writing it into their UserData.

    Every bit of UserData outside the palette and finish fields is kept.

    Returns:
        tuple: (number coloured, number whose UserData did not resolve)
    """
    pairs = []
    for bpy_object in objects:
        value = encode(bpy_object.get(PROP_USER_DATA, 0), colour_index, material_index)
        bpy_object[PROP_USER_DATA] = str(value)
        pairs.append((bpy_object, value))
    return apply_many(pairs, tag=tag)


def recolour_from_user_data(objects, user_data_value, tag=True):
    """Set objects to an exact UserData value, e.g. copied from another part.

    A value that does not resolve leaves every object untouched rather than
    stamping an unusable value into their UserData.

    Returns:
        tuple: (number coloured, number whose UserData did not resolve)
    """
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
        done += 1
    return done, failed


def default_user_data(object_id):
    """The UserData the game gives a freshly placed part."""
    return game_data.default_user_data(object_id)


def clear(bpy_object):
    """Strip the colour properties, returning an object to its raw textures.

    An absent slot property reads as black inside the node group, so removing
    them also clears any stale colour rather than leaving it half applied.
    """
    for prop in SLOT_PROPS + (PROP_FINISH,):
        if prop in bpy_object:
            del bpy_object[prop]
    strip_legacy_finish_props([bpy_object])
    bpy_object.update_tag()


# Viewport ---
def use_object_colour_in_viewport(enable=True, only_solid=True):
    """Point Solid viewport shading at the per object colour.

    High res parts share their materials, so under MATERIAL colour they all
    draw the same. OBJECT reads object.color instead, which both systems set.
    Textured and Rendered shading are unaffected.

    Returns:
        int: How many viewports were changed.
    """
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
                if shading.color_type != colour_type:
                    shading.color_type = colour_type
                    changed += 1
    return changed
