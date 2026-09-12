"""Charon Forge's part colouring.

    paths.py         where the colour data is on disk
    properties.py    names shared with the asset files, shaders and objects
    palettes.py      the game's colour tables, and reading UserData against them
    finishes.py      what each finish does to a high res part's surface
    colouring.py     colouring high res parts through object properties
    finish_nodes.py  the shader nodes that let a finish change a surface
    dedupe.py        collapsing the textures and node groups appends duplicate
    deferral.py      running those whole-library passes once per bulk build
    flat.py          MaterialProvider - flat materials for proxies and lines
    mixin.py         HighResMaterialsMixin - high res parts routed to
                     colouring.py, layered onto any provider class
    host.py          the same, onto the base builder addon's MaterialProvider,
                     for its set_material_provider() hook

Charon Forge's own code calls the functions below. The flat material ones go
through the active provider, a CharonMaterials unless set_provider() swapped it.
"""

from . import host
from .colouring import (apply, apply_many, apply_palette, clear, is_colourable,
                        is_high_res, recolour, recolour_from_user_data,
                        use_object_colour_in_viewport)
from .dedupe import dedupe_appended_data, dedupe_images, dedupe_node_groups
from .deferral import defer_shared_data, note_appended_data
from .finish_nodes import ensure_finish_nodes
from .finishes import FINISH_NEUTRAL, get_finish, get_finish_table
from .flat import MaterialProvider, optimise_materials
from .mixin import HighResMaterialsMixin
from .palettes import (BAKED_COLOURS, BAKED_INDEX_COLOURS, BAKED_PALETTES,
                       BAKED_PALETTES_UI, darken_color, decode_user_data,
                       get_colours_from_palette, get_nice_name_from_indicies,
                       get_nice_names, get_palette)
from .properties import (COLOURISE_GROUP, MESH_TAG, PROP_READONLY_COLOUR,
                         PROP_READONLY_MATERIAL, SLOT_PROPS)


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
