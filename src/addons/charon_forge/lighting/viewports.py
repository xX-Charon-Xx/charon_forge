"""Making the 3D views show the game lighting, and giving them back.

The rig is invisible where Blender does not look at it: Solid and Wireframe
shading draw no lighting at all, and Material Preview lights with Blender's
own studio HDRI unless its shading says to use the scene's lights and world
(Rendered has its own pair of the same switches). So turning the rig on, in
every 3D view showing the scene:

    Solid / Wireframe  -> Material Preview
    scene lights and world, for Material Preview and Rendered -> on

and `remember` stores what each view had, so `restore` puts the scene light
and world switches back when the rig is turned off. The shading itself is
left as it is: a view the rig moved to Material Preview stays there (the
user's call, 2026-09-29). Views are keyed by screen name and area index - an area
has no name of its own - and a view that has gone since is simply skipped.
"""

import bpy

FLAGS = ("use_scene_lights", "use_scene_world",
         "use_scene_lights_render", "use_scene_world_render")
UNLIT_SHADING = {"SOLID", "WIREFRAME"}


def scene_views(scene):
    """(screen name, area index, shading) of every 3D view showing the scene."""
    wm = getattr(bpy.context, "window_manager", None)
    for window in (wm.windows if wm else []):
        if window.scene != scene:
            continue
        for index, area in enumerate(window.screen.areas):
            if area.type == "VIEW_3D":
                yield window.screen.name, index, area.spaces[0].shading


def remember(scene):
    """What every view has now, as ID-property-safe data (no mixed lists)."""
    return [{"screen": screen, "area": index,
             "flags": [int(bool(getattr(shading, f, False))) for f in FLAGS]}
            for screen, index, shading in scene_views(scene)]


def show_game_lighting(scene):
    """Every view of the scene to Material Preview (unless it already shows
    lighting) with the scene's lights and world."""
    for _, _, shading in scene_views(scene):
        if shading.type in UNLIT_SHADING:
            shading.type = "MATERIAL"
        for flag in FLAGS:
            if hasattr(shading, flag) and not getattr(shading, flag):
                setattr(shading, flag, True)


def restore(scene, saved):
    """Give every view back its scene light and world switches - not its
    shading, which stays in Material Preview."""
    by_view = {(row["screen"], row["area"]): row for row in saved or []}
    for screen, index, shading in scene_views(scene):
        row = by_view.get((screen, index))
        if row is None:
            continue
        for flag, value in zip(FLAGS, list(row["flags"])):
            if hasattr(shading, flag):
                setattr(shading, flag, bool(value))


def needs_switch(shading):
    """True when this view would not show the rig: the panel then offers one
    button that runs show_game_lighting."""
    if shading is None:
        return False
    if shading.type in UNLIT_SHADING:
        return True
    return shading.type == "MATERIAL" and not (shading.use_scene_world
                                               and shading.use_scene_lights)
