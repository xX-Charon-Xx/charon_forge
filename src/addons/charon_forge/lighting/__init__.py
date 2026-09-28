"""Charon Forge's game lighting: the game's skies, sun and lamps in Blender.

    data.py         resources/lighting/lighting.json and its textures, written
                    by the extraction pipeline (pipeline/outputs/lighting.py)
                    from the game's sky tables
    sky.py          the "Charon Sky" world - planet sky, space sky, HDRI
    game_lights.py  the parts' game lamps as lights, in their own collection
    rig.py          settings -> world, sun and view (apply / enable / disable)
    properties.py   scene.charon_lighting, context defaults and user presets

The panel is in The Watchtower (addon/the_watchtower_presentation.py).
docs/LIGHTING.md at the top of the repository explains the whole system.
"""

from . import data, game_lights, properties, rig, sky


def register():
    properties.register()


def unregister():
    properties.unregister()
