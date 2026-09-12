import os

import bpy
from bpy.props import PointerProperty

from . import addon_preferences, hooks
from .addon import (asset_browser, asset_browser_operators,
                    asset_browser_presentation, header, header_operators,
                    header_presentation)
from .addon.asset_browser import AssetBrowser
from .addon.header import Header
from .addon_preferences import CharonAddonPreferences
from .menu import base_builder_menu, base_builder_menu_operators
from .objects import preset
from .tools.batch_tool import BatchTool
from .utils import icon_utils, themes_util

FILE_PATH = os.path.dirname(os.path.realpath(__file__))


# Plugin Registration ---

classes = (
    CharonAddonPreferences,
    BatchTool,
)

classes = classes + header.classes + header_operators.classes + header_presentation.classes
classes = (
    classes
    + asset_browser.classes
    + asset_browser_operators.classes
    + asset_browser_presentation.classes
    + base_builder_menu.classes
    + base_builder_menu_operators.classes
)


def register():
    icon_utils.register_icons()

    # builder.py/preset.py assume ~/CharonForge/(mods|presets) exist
    os.makedirs(preset.Preset.PRESET_PATH, exist_ok=True)

    # Register Plugin
    for _class in classes:
        bpy.utils.register_class(_class)
    bpy.types.Scene.nms_batch_tool = PointerProperty(type=BatchTool)

    # blender's interface theme is an application setting, not saved with a
    # .blend, so unlike the rest of what's registered above it needs actively
    # putting back: the preferences page remembers which one was chosen, but
    # only re-applying it here makes the colours agree with that on a plain
    # restart where the theme itself did not carry over.
    prefs = addon_preferences.get_addon_preferences()
    if prefs is not None:
        themes_util.apply_named_theme(prefs.theme)

    bpy.types.Scene.charon_header = PointerProperty(type=Header)
    bpy.types.Scene.nms_asset_browser = PointerProperty(type=AssetBrowser)

    # the "Builder" and "I/O" dropdowns in the 3D viewport's header
    base_builder_menu.register_menu()

    # hand our builder and materials to the base builder addon, so its own
    # panels work on Charon Forge's parts
    hooks.install()


def unregister():
    hooks.remove()

    base_builder_menu.unregister_menu()

    del bpy.types.Scene.nms_asset_browser
    del bpy.types.Scene.charon_header
    del bpy.types.Scene.nms_batch_tool

    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)

    icon_utils.unregister_icons()


if __name__ == "__main__":
    register()
