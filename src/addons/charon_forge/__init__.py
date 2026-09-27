import os

import bpy

from . import hooks, materials
from .addon import asset_browser
from .addon import crossing
from .addon import header
from .addon import helmsman
from .addon import optimiser
from .addon import the_forge
from .addon import the_watchtower
from .addon_preferences import CharonAddonPreferences
from .menu import base_builder_menu, base_builder_menu_operators
from .objects import preset
from . import save_editor
from .utils import icon_utils

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


def _register_class(_class):
    # A class of ours can still be registered from an earlier enable that
    # failed partway, or from the version this one replaced without a
    # restart. Registering again then fails with "already registered as a
    # subclass", hiding whatever went wrong the first time.
    stale = getattr(bpy.types, _class.__name__, None)
    if stale is not None and getattr(stale, "bl_idname", None) == getattr(_class, "bl_idname", None):
        try:
            bpy.utils.unregister_class(stale)
        except RuntimeError:
            pass
    bpy.utils.register_class(_class)


def register():
    try:
        _register()
    except Exception:
        # leave nothing half registered, so enabling again shows this error
        # rather than one about classes that are still registered
        _unregister(ignore_errors=True)
        raise


def _register():
    icon_utils.register_icons()

    # builder.py/preset.py assume ~/CharonForge/(mods|presets) exist
    os.makedirs(preset.Preset.PRESET_PATH, exist_ok=True)

    # Register Plugin
    for _class in classes:
        _register_class(_class)

    # the chosen theme is only applied when it is picked from the list (see
    # addon_preferences.on_theme_update), never re-applied on startup, so a
    # theme changed elsewhere in Preferences is left alone on restart

    save_editor.register()
    header.register()
    optimiser.register()
    the_forge.register()
    the_watchtower.register()
    crossing.register()
    helmsman.register()
    
    materials.register()
    asset_browser.register()

    # the "Builder" and "I/O" dropdowns in the 3D viewport's header
    base_builder_menu.register_menu()

    # hand our builder and materials to the base builder addon, so its own
    # panels work on Charon Forge's parts
    hooks.install()


def unregister():
    _unregister()


def _unregister(ignore_errors=False):
    steps = [
        hooks.remove,
        base_builder_menu.unregister_menu,
        asset_browser.unregister,
        materials.unregister,
        the_watchtower.unregister,
        the_forge.unregister,
        crossing.unregister,
        helmsman.unregister,
        optimiser.unregister,
        header.unregister,
        save_editor.unregister,
    ]
    steps += [
        (lambda _class=_class: bpy.utils.unregister_class(_class))
        for _class in reversed(classes)
    ]
    steps.append(icon_utils.unregister_icons)

    for step in steps:
        try:
            step()
        except Exception:
            # after a failed register some of these were never registered
            if not ignore_errors:
                raise


if __name__ == "__main__":
    register()
