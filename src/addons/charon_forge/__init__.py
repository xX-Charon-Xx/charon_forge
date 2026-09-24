import os

import bpy

from . import addon_preferences, hooks, materials
from .addon import asset_browser
from .addon import crossing
from .addon import header
from .addon import helmsman
from .addon import optimiser
from .addon_preferences import CharonAddonPreferences
from .menu import base_builder_menu, base_builder_menu_operators
from .objects import preset
from . import save_editor
from .utils import icon_utils, themes_util

FILE_PATH = os.path.dirname(os.path.realpath(__file__))


# Plugin Registration ---
#
# BatchTool is not one of ours any more - the base builder addon registers
# scene.nms_batch_tool itself, and we call into that through
# base_builder_utils.get_batch_tool() instead of shipping a second copy.

classes = (
    CharonAddonPreferences,
)

classes = (
    classes
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

    # blender's interface theme is an application setting, not saved with a
    # .blend, so unlike the rest of what's registered above it needs actively
    # putting back: the preferences page remembers which one was chosen, but
    # only re-applying it here makes the colours agree with that on a plain
    # restart where the theme itself did not carry over.
    prefs = addon_preferences.get_addon_preferences()
    if prefs is not None:
        themes_util.apply_named_theme(prefs.theme)

    save_editor.register()
    header.register()
    optimiser.register()
    helmsman.register()
    crossing.register()
    materials.register()
    asset_browser.register()

    # the "Builder" and "I/O" dropdowns in the 3D viewport's header
    base_builder_menu.register_menu()

    # hand our builder and materials to the base builder addon, so its own
    # panels work on Charon Forge's parts
    hooks.install()


def unregister():
    hooks.remove()

    base_builder_menu.unregister_menu()

    asset_browser.unregister()
    materials.unregister()
    crossing.unregister()
    helmsman.unregister()
    optimiser.unregister()
    header.unregister()
    save_editor.unregister()

    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)

    icon_utils.unregister_icons()


if __name__ == "__main__":
    register()
