"""Mostly the base builder addon's utils.collection_utils, forwarded rather
than duplicated - see base_builder_utils's module docstring.

set_collection_visibility() is the one function the host addon does not have,
so it stays implemented here; everything else (get_collection,
move_object_into_collection, and so on) is a straight passthrough - to
utils/fallbacks/collection_utils.py while the host addon isn't loaded.
"""

import bpy

from .base_builder_utils import get_module

_RELATIVE_PATH = "utils.collection_utils"

# Matches the host addon's own names for these, so curve.py (ported alongside
# it) can keep referring to collection_utils.LINKED_CURVE_OBJ_COL unchanged.
LINKED_CURVE_OBJ_COL = "Linked Curve Objects"
UNLINKED_CURVE_OBJ_COL = "Unlinked Curve Objects"


def get_collection(collection_name):
    return __getattr__("get_collection")(collection_name)


def set_collection_visibility(collection_name="Collection", visible=True):
    """Whether a collection is included in the active view layer.

    Args:
        collection_name (str): Target collection's name.
        visible (bool): True to show/include in the view layer, False to
            hide/exclude it.
    """
    target_collection = get_collection(collection_name)
    if not target_collection:
        return

    layer_collection = bpy.context.view_layer.layer_collection.children.get(
        target_collection.name
    )
    if layer_collection:
        layer_collection.exclude = not visible


def __getattr__(name):
    module = get_module(_RELATIVE_PATH)
    if module is None or not hasattr(module, name):
        from .fallbacks import collection_utils as module
    if not hasattr(module, name):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(module, name)
