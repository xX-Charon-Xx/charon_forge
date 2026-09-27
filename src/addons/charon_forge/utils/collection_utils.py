"""Mostly the base builder addon's utils.collection_utils, forwarded rather
than duplicated - see base_builder_utils's module docstring.

set_collection_visibility() is the one function the host addon does not have,
so it stays implemented here; everything else (get_collection,
move_object_into_collection, and so on) is a straight passthrough - to
utils/fallbacks/collection_utils.py while the host addon isn't loaded.
"""

import contextlib

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


def _layer_collections(layer_collection):
    yield layer_collection
    for child in layer_collection.children:
        yield from _layer_collections(child)


@contextlib.contextmanager
def excluded_from_view_layer(*collections):
    """Keep collections out of the active view layer while a block builds
    into them, then put each back the way it was.

    Objects linked into an excluded collection are not evaluated, drawn or
    synced to the view layer as they arrive; that happens once, when the
    block ends, instead of after each one. Anything excluded before the block
    stays excluded after it.

    Hiding (H), selection and the active object belong to the view layer, and
    Blender drops them for objects that leave it - so they are read before
    and written back after, for every object in these collections.

    Nothing inside the block can select, hide or make active an object that
    is only in these collections - those need the view layer.
    """
    view_layer = bpy.context.view_layer
    wanted = {collection for collection in collections if collection is not None}
    previous = []
    for layer_collection in _layer_collections(view_layer.layer_collection):
        if layer_collection.collection in wanted and not layer_collection.exclude:
            previous.append(layer_collection)

    hidden, selected = [], []
    for obj in {obj for lc in previous for obj in lc.collection.all_objects}:
        try:
            if obj.hide_get(view_layer=view_layer):
                hidden.append(obj)
            if obj.select_get(view_layer=view_layer):
                selected.append(obj)
        except RuntimeError:
            continue                    # not in this view layer after all
    active = view_layer.objects.active

    for layer_collection in previous:
        layer_collection.exclude = True
    try:
        yield
    finally:
        for layer_collection in previous:
            try:
                layer_collection.exclude = False
            except ReferenceError:
                continue
        for objects, restore in ((hidden, lambda o: o.hide_set(True, view_layer=view_layer)),
                                 (selected, lambda o: o.select_set(True, view_layer=view_layer))):
            for obj in objects:
                try:
                    restore(obj)
                except (ReferenceError, RuntimeError):
                    continue            # removed, or no longer in the layer
        if active is not None and view_layer.objects.active is None:
            try:
                view_layer.objects.active = active
            except (ReferenceError, RuntimeError, TypeError):
                pass


def __getattr__(name):
    module = get_module(_RELATIVE_PATH)
    if module is None or not hasattr(module, name):
        from .fallbacks import collection_utils as module
    if not hasattr(module, name):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(module, name)
