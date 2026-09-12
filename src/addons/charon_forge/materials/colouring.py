"""Colouring parts from the high res library.

The flat materials (flat.py) paint a part by swapping a flat coloured material
into slot 0. That works for the flat fbx proxies, but it throws away the real
game textures and it forces one material - and therefore one mesh datablock -
per (ObjectID, UserData) pair.

The high res library works the other way round. Every colourable material in
it carries an "NMS_Colourise" node group whose four palette slots are Attribute
nodes of type OBJECT, reading the object custom properties nms_p / nms_s /
nms_t / nms_q. So the colour lives on the OBJECT, not on the material, and
colouring a part is four property writes - no material is touched and nothing
has to be duplicated.

That is what makes the whole thing cheap: a thousand placements of the same
part share ONE mesh and ONE set of materials and can still each be a different
colour. Never copy a mesh or a material just to recolour something here.
"""

import bpy

from ..nms.utils import userdata
from . import finishes, palettes
from .finish_nodes import ensure_finish_nodes
from .properties import (COLOURISE_GROUP, MESH_TAG, PROP_FINISH_METALLIC,
                         PROP_FINISH_POLISH, PROP_FINISH_ROUGHNESS,
                         PROP_FINISH_TINT, PROP_FINISH_TINT_MIX,
                         PROP_READONLY_COLOUR, PROP_READONLY_MATERIAL,
                         PROP_USER_DATA, SLOT_ORDER, SLOT_ORDER_INVERTED,
                         SLOT_PROPS)


# Telling the systems apart ---
def is_high_res(bpy_object):
    """Check whether an object came out of the high res library.

    This is the test the flat material code uses to decide whether it may
    paint a flat material over something. It asks where the part came from
    rather than whether it happens to be colourable, because a high res part
    with no colourable material still must not be flattened - in game those
    parts just cannot be recoloured.

    Returns:
        bool: True if its mesh carries the high res marker.
    """
    data = getattr(bpy_object, "data", None)
    return data is not None and MESH_TAG in data


def is_colourable(bpy_object):
    """Check whether an object actually responds to the colour properties.

    Returns:
        bool: True if any of its materials carries the colourise node group.
    """
    for slot in bpy_object.material_slots:
        material_data = slot.material
        if material_data is None or material_data.node_tree is None:
            continue
        for node in material_data.node_tree.nodes:
            if node.type != "GROUP" or node.node_tree is None:
                continue
            if node.node_tree.name.startswith(COLOURISE_GROUP):
                return True
    return False


# Applying colour ---
def apply_palette(bpy_object, palette, finish=None):
    """Write the four palette slots and the surface finish onto an object.

    Args:
        bpy_object (bpy.types.Object): The object to colour.
        palette (dict): A palette entry with p/s/t/q RGBA lists.
        finish (dict): An entry from finishes.json. Defaults to neutral.
    """
    finish = finish if finish is not None else finishes.FINISH_NEUTRAL

    slots = SLOT_ORDER_INVERTED if finish.get("invert") else SLOT_ORDER
    for prop_name, slot in zip(SLOT_PROPS, slots):
        bpy_object[prop_name] = tuple(palette[slot])
    primary = tuple(palette[slots[0]])

    # Offsets rather than absolute values, so a part keeps the surface detail
    # its own maps give it. 0 is "unchanged", which is also what the shader
    # reads for an object that has never been given a finish.
    bpy_object[PROP_FINISH_ROUGHNESS] = float(finish.get("roughness", 0.0))
    bpy_object[PROP_FINISH_METALLIC] = float(finish.get("metallic", 0.0))
    bpy_object[PROP_FINISH_POLISH] = float(finish.get("polish", 0.0))
    bpy_object[PROP_FINISH_TINT] = tuple(finish.get("tint", (0.0, 0.0, 0.0)))
    bpy_object[PROP_FINISH_TINT_MIX] = float(finish.get("tint_mix", 0.0))

    # Solid viewport shading set to Object colour draws this, so parts can still
    # be told apart at a glance without waiting for textures. A high res part
    # shares its materials with every other placement of that id, so the
    # viewport colour has to live on the object - the same reason the palette
    # slots do. Primary is the part's body colour, so it is the one that reads
    # as "what colour is this part".
    bpy_object.color = primary


def _write_labels(bpy_object, names):
    bpy_object[PROP_READONLY_COLOUR] = names[0] or ""
    bpy_object[PROP_READONLY_MATERIAL] = names[1] or ""


def apply(bpy_object, user_data_value, tag=True):
    """Colour a single object from a UserData value.

    Args:
        bpy_object (bpy.types.Object): The object to colour.
        user_data_value: The packed UserData value.
        tag (bool): Flag the object for a depsgraph re-evaluation. Skip this
            while bulk building - one view layer update at the end is enough.

    Returns:
        dict: The palette that was applied, or None if it didn't resolve, in
            which case the object is left untouched.
    """
    palette = palettes.get_palette(user_data_value)
    if palette is None:
        return None

    apply_palette(bpy_object, palette, finishes.get_finish(user_data_value))
    _write_labels(bpy_object, palettes.get_nice_names(user_data_value))
    if tag:
        bpy_object.update_tag()
    return palette


def apply_many(pairs, tag=False, update=False):
    """Colour a lot of objects at once.

    Each distinct UserData value is resolved once and reused, so the per object
    cost is just the four property writes.

    Args:
        pairs (iterable): An iterable of (bpy object, UserData value).
        tag (bool): Flag each object for re-evaluation as it goes.
        update (bool): Push a single view layer update when finished.

    Returns:
        tuple: (number coloured, number whose UserData didn't resolve)
    """
    cache = {}
    applied = 0
    unresolved = 0

    for bpy_object, user_data_value in pairs:
        key = str(user_data_value)
        if key not in cache:
            names = palettes.get_nice_names(key)
            cache[key] = (palettes.get_palette(key), names,
                          finishes.get_finish_by_name(names[1]))
        palette, names, finish = cache[key]

        if palette is None:
            unresolved += 1
            continue

        apply_palette(bpy_object, palette, finish)
        _write_labels(bpy_object, names)
        if tag:
            bpy_object.update_tag()
        applied += 1

    if update:
        bpy.context.view_layer.update()

    return applied, unresolved


def recolour(objects, colour_index=None, material_index=None, tag=True):
    """Repaint objects, writing the new indices into their UserData first.

    The high res counterpart of assigning a flat material. Nothing is copied
    and no material is touched, so a hundred selected parts stay on the meshes
    they were already sharing - which is the whole point of the object
    property approach.

    Every bit of UserData outside the colour and finish fields is preserved,
    including the reserved ones, exactly as nms/utils/userdata.py intends.

    Args:
        objects (iterable): The objects to repaint.
        colour_index (int): The new colour index, or None to leave it alone.
        material_index (int): The new finish index, or None to leave it alone.
        tag (bool): Flag each object for a depsgraph re-evaluation.

    Returns:
        tuple: (number coloured, number whose UserData didn't resolve)
    """
    pairs = []
    for bpy_object in objects:
        try:
            current = int(bpy_object.get(PROP_USER_DATA, 0) or 0)
        except (TypeError, ValueError):
            current = 0

        value = userdata.update_colour_material(
            current, colour_index=colour_index, material_index=material_index
        )
        bpy_object[PROP_USER_DATA] = str(value)
        pairs.append((bpy_object, value))

    # A base saved before finishes were handled has materials with no finish
    # nodes in them, so the offsets would land on nothing. Cheap to call again -
    # materials that already have them carry a marker - so the first recolour
    # after opening such a file quietly brings it up to date.
    ensure_finish_nodes()

    return apply_many(pairs, tag=tag)


def recolour_from_user_data(objects, user_data_value, tag=True):
    """Repaint objects to an exact UserData value.

    Used when the value is already known, such as the colour picker copying
    one part's look onto another.

    A value that doesn't resolve to a palette - None, or an index outside the
    table - leaves every object completely untouched, rather than stamping an
    unusable value into their UserData.

    Returns:
        tuple: (number coloured, number whose UserData didn't resolve)
    """
    objects = list(objects)

    # one value for all of them, so resolve it once and bail if it is no good
    palette = palettes.get_palette(user_data_value)
    if palette is None:
        return 0, len(objects)

    names = palettes.get_nice_names(user_data_value)
    finish = finishes.get_finish_by_name(names[1])
    value = str(user_data_value)

    # see recolour() - keeps an older file working the moment it is touched
    ensure_finish_nodes()

    for bpy_object in objects:
        bpy_object[PROP_USER_DATA] = value
        apply_palette(bpy_object, palette, finish)
        _write_labels(bpy_object, names)
        if tag:
            bpy_object.update_tag()

    return len(objects), 0


def clear(bpy_object):
    """Strip the colour properties, returning an object to its raw textures.

    An absent slot property reads as black inside the node group, so removing
    them also clears any stale colour rather than leaving it half applied.
    """
    for prop in SLOT_PROPS:
        if prop in bpy_object:
            del bpy_object[prop]
    bpy_object.update_tag()


# Viewport ---
def use_object_colour_in_viewport(enable=True, only_solid=True):
    """Point Solid viewport shading at the per object colour.

    Blender's Solid mode defaults to colouring by MATERIAL, which is what made
    the flat material system readable - every part had its own material
    carrying its diffuse_color. High res parts share their materials, so under
    MATERIAL they all draw the same and the scene turns into one grey mass.
    OBJECT reads object.color instead, which both systems set.

    Textured and Rendered shading are unaffected either way.

    Args:
        enable (bool): True for OBJECT colour, False back to MATERIAL.
        only_solid (bool): Skip viewports that aren't in Solid shading, so a
            viewport somebody has deliberately put in Material Preview or
            Rendered is left alone.

    Returns:
        int: How many viewports were changed. Zero in background mode, which
            has no windows.
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
