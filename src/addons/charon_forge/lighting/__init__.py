"""Charon Forge's game lighting: the game's skies, sun and lamps in Blender.
UI is in addon/the_watchtower_lighting_*.py; docs/LIGHTING.md explains it all."""

from . import (data, game_lights, presets, previews, properties, rig, sky,
               viewports)


def register():
    properties.register()


def unregister():
    properties.unregister()
    previews.unregister()
