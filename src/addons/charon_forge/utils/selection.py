"""Selecting one object without touching the rest of the scene.

The base builder addon's blend_utils.select() deselects with
bpy.ops.object.select_all, which tags EVERY object in the view layer for a
depsgraph update. Its curve_udpate_handler then walks all of those updates
and looks each object up by name. Measured at 1500 parts that was ~0.11s for
the deselect plus ~0.17s of handler per click, the largest part of placing a
part from the asset browser - and it grows with the scene, not the part.

Only the objects that actually were selected need deselecting, so that is
all this touches.
"""

import bpy


def select_only(bpy_object):
    """Make `bpy_object` the only selected object, and the active one."""
    view_layer = bpy.context.view_layer
    for other in list(view_layer.objects.selected):
        if other != bpy_object:
            other.select_set(False)
    bpy_object.select_set(True)
    view_layer.objects.active = bpy_object
