"""Charon Forge's part colouring, finishes and glow.

    paths.py         where the colour data is on disk
    properties.py    names shared with the asset files, shaders and objects
    game_data.py     the game's palettes, finishes and per part groups
                     (resources/colours.json, written by the extraction
                     pipeline from the game files)
    colouring.py     colouring high res parts through object properties
    colourise.py     a primary tint for colourable materials with no mask
    emission.py      making what glows in game glow in Blender
    finish_nodes.py  tearing the old hand-tuned finish preview out of old files
    palettes.py      DT_Palettes.csv, for the flat proxy materials only
    dedupe.py        collapsing the textures and node groups appends duplicate
    deferral.py      running those whole-library passes once per bulk build
    flat.py          MaterialProvider - flat materials for proxies and lines
    mixin.py         HighResMaterialsMixin - high res parts routed to
                     colouring.py, layered onto any provider class
    host.py          the same, onto the base builder addon's MaterialProvider,
                     for its set_material_provider() hook

docs/MATERIALS.md at the top of the repository explains the whole system.
"""

import bpy

from . import colourise, emission, game_data, host
from .colouring import (apply, apply_many, apply_palette, clear, decode,
                        default_user_data, encode, is_colourable, is_high_res,
                        object_id_of, recolour, recolour_from_user_data,
                        resolve, use_object_colour_in_viewport)
from .dedupe import dedupe_appended_data, dedupe_images, dedupe_node_groups
from .deferral import defer_shared_data, note_appended_data, should_defer
from .finish_nodes import strip_legacy_finish_nodes
from .flat import MaterialProvider, optimise_materials
from .mixin import HighResMaterialsMixin
from .palettes import (BAKED_COLOURS, BAKED_INDEX_COLOURS, BAKED_PALETTES,
                       BAKED_PALETTES_UI, darken_color, get_colours_from_palette,
                       get_nice_name_from_indicies)
from .properties import (COLOURISE_GROUP, MESH_TAG, PROP_FINISH,
                         PROP_READONLY_COLOUR, PROP_READONLY_MATERIAL,
                         PROP_USER_DATA, SLOT_PROPS)


def prepare_materials(materials=None):
    """The per-material pass after assets are appended: take the old finish
    splice out of anything that still has it, tint colourable materials that
    have no colourise mask, and wire emission where the game draws a glow.
    Idempotent - each material is tagged once done.

    With no argument it walks every material in the file, so inside
    defer_shared_data() it waits for the end of the block.

    Returns:
        int: Materials changed.
    """
    if materials is None and should_defer():
        return 0
    # the tint goes in before emission, so a glow copies the tinted colour
    return (strip_legacy_finish_nodes(materials)
            + colourise.ensure_colourise(materials)
            + emission.ensure_emission(materials))


# the name the callers used before; the finish is textures now, not nodes
ensure_finish_nodes = prepare_materials


class CharonMaterials(HighResMaterialsMixin, MaterialProvider):
    """Charon Forge's materials: flat materials, with high res parts coloured
    through object properties."""


_default_provider = None
_active_provider = None


def get_provider():
    """The material provider Charon Forge's own code paints with."""
    global _default_provider, _active_provider
    if _active_provider is None:
        if _default_provider is None:
            _default_provider = CharonMaterials()
        _active_provider = _default_provider
    return _active_provider


def set_provider(provider):
    """Swap the provider. None restores CharonMaterials."""
    global _active_provider
    if provider is not None and not isinstance(provider, MaterialProvider):
        raise TypeError("set_provider expects a MaterialProvider instance or None")
    _active_provider = provider


# Flat materials, forwarded to the active provider ---
def validate_material(colour_name, colour_value):
    return get_provider().validate_material(colour_name, colour_value)


def set_material(item, material):
    return get_provider().set_material(item, material)


def assign_power_material(item):
    return get_provider().assign_power_material(item)


def assign_portal_material(item):
    return get_provider().assign_portal_material(item)


def assign_pipe_material(item):
    return get_provider().assign_pipe_material(item)


def assign_bytebeat_material(item):
    return get_provider().assign_bytebeat_material(item)


def assign_preset_material(item):
    return get_provider().assign_preset_material(item)


def assign_default_material(item, index=0):
    return get_provider().assign_default_material(item, index=index)


def get_colour_from_palette_data(colour_index, material_index):
    return get_provider().get_colour_from_palette_data(colour_index, material_index)


def restore_material(item, user_data_value):
    return get_provider().restore_material(item, user_data_value)


def assign_material(item, colour_index=0, material_index=0):
    return get_provider().assign_material(item, colour_index, material_index)


create_host_material_provider = host.create_host_material_provider
create_host_material_provider_class = host.create_host_material_provider_class


# File handlers ---
@bpy.app.handlers.persistent
def _on_load(_filepath=None):
    """A scene opened from disk: bring its materials up to date - old finish
    nodes out, maskless colourable materials tinted, glow in."""
    try:
        prepare_materials()
        for mesh in bpy.data.meshes:
            if MESH_TAG in mesh and emission.GLOW_LAMP_PROP not in mesh:
                emission.stamp_glow(mesh, mesh[MESH_TAG])
    except Exception as exc:                              # noqa: BLE001
        print("Charon Forge: could not update materials on load: %r" % exc)


def register():
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)


def unregister():
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
