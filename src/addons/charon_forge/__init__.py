import os

import bpy
from bpy.props import PointerProperty

from . import addon_preferences, hooks, nms
from .addon import (asset_browser, asset_browser_operators,
                    asset_browser_presentation, header, header_operators,
                    header_presentation)
from .addon.asset_browser import AssetBrowser
from .addon.header import Header
from .addon_preferences import CharonAddonPreferences
from .menu import base_builder_menu, base_builder_menu_operators
from .utils import icon_utils

FILE_PATH = os.path.dirname(os.path.realpath(__file__))


# Plugin Registration ---

classes = (
    CharonAddonPreferences,
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

    # Register Plugin
    for _class in classes:
        bpy.utils.register_class(_class)
    bpy.types.Scene.charon_header = PointerProperty(type=Header)
    bpy.types.Scene.nms_asset_browser = PointerProperty(type=AssetBrowser)

    nms.register()

    # the "Builder" and "I/O" dropdowns in the 3D viewport's header
    base_builder_menu.register_menu()

    # hand our builder and materials to the base builder addon, so its own
    # panels work on Charon Forge's parts
    hooks.install()


def unregister():
    hooks.remove()

    base_builder_menu.unregister_menu()

    nms.unregister()

    del bpy.types.Scene.nms_asset_browser
    del bpy.types.Scene.charon_header

    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)

    icon_utils.unregister_icons()


if __name__ == "__main__":
    register()
