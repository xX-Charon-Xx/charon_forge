import bpy

from .. import lighting
from ..utils import viewport_overlay
from . import (the_watchtower_lighting_operators,
               the_watchtower_lighting_presentation, the_watchtower_operators,
               the_watchtower_presentation)

# The Watchtower's overlay keeps no state of its own - what it shows, and
# where, is in the addon preferences (watchtower_*), so it holds across files
# and restarts. Its Game Lighting keeps scene.charon_lighting (lighting/).

# the panel before its Advanced sub-panel
classes = (the_watchtower_operators.classes
           + the_watchtower_lighting_operators.classes
           + the_watchtower_presentation.classes
           + the_watchtower_lighting_presentation.classes)


def register():
    # scene.charon_lighting - the Game Lighting settings
    lighting.register()
    for _class in classes:
        bpy.utils.register_class(_class)
    # on a timer: while blender is still bringing addons up there are no
    # viewports to redraw yet
    bpy.app.timers.register(viewport_overlay.register_draw, first_interval=0.01)


def unregister():
    if bpy.app.timers.is_registered(viewport_overlay.register_draw):
        bpy.app.timers.unregister(viewport_overlay.register_draw)
    viewport_overlay.unregister_draw()
    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)
    lighting.unregister()
