"""Selecting one object by deselecting only what was selected, which is much faster
than select_all on big scenes."""

import bpy


def select_only(bpy_object):
    """Make `bpy_object` the only selected object, and the active one."""
    view_layer = bpy.context.view_layer
    for other in list(view_layer.objects.selected):
        # a just-removed object can still be listed, as None
        if other is not None and other != bpy_object:
            other.select_set(False)
    bpy_object.select_set(True)
    view_layer.objects.active = bpy_object
