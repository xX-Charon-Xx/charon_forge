"""Charon Forge's game lighting: the game's skies, sun and lamps in Blender.

    data.py         resources/lighting/lighting.json and its textures, written
                    by the extraction pipeline (pipeline/outputs/lighting.py)
                    from the game's sky tables
    sky.py          the "Charon Sky" world - planet sky, space sky + nebula
    previews.py     the sky pickers' preview swatches
    game_lights.py  the parts' game lamps as lights, in their own collection
    viewports.py    the 3D views: shown the lighting, and given back
    rig.py          settings -> world, sun and view (enable / disable / apply)
    properties.py   scene.charon_lighting, place defaults, quick actions
    presets.py      user presets on disk

The UI is in addon/the_watchtower_lighting_presentation.py and
addon/the_watchtower_lighting_operators.py, drawn into The Watchtower panel.
docs/LIGHTING.md at the top of the repository explains the whole system.
"""

from . import (data, game_lights, presets, previews, properties, rig, sky,
               viewports)


def register():
    properties.register()


def unregister():
    properties.unregister()
    previews.unregister()
