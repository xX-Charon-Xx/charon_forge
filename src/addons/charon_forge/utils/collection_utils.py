"""Forwards to the base builder addon's utils.collection_utils (or the fallback),
plus the few collection helpers the host addon doesn't have."""

import contextlib

import bpy

from .base_builder_utils import get_module

_RELATIVE_PATH = "utils.collection_utils"

# same names as the host addon's, so curve.py can use them unchanged
LINKED_CURVE_OBJ_COL = "Linked Curve Objects"
UNLINKED_CURVE_OBJ_COL = "Unlinked Curve Objects"


def get_collection(collection_name):
    return __getattr__("get_collection")(collection_name)


def set_collection_visibility(collection_name="Collection", visible=True):
    """Include or exclude a collection from the active view layer."""
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
    """Exclude collections from the view layer while a block builds into them, so the
    sync happens once; hiding, selection and the active object are restored after."""
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
