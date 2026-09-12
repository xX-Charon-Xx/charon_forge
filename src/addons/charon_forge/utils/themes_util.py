"""Apply Blender interface themes (.xml) from a known file path.

Blender's exported theme files use a .xml extension, but are actually
executed as python via the same "preset" mechanism as any other preset
(bpy.ops.script.execute_preset just execs the file's contents). These
helpers wrap that so a theme can be applied from a known path without
going through Preferences > Themes.
"""

import json
import os
import shutil

import bpy

# the menu blender uses for the built-in "Interface Theme" preset dropdown,
# its preset_subdir ("interface_theme") is where installed themes live
THEME_PRESET_MENU = "USERPREF_MT_interface_theme_presets"
THEME_PRESET_SUBDIR = "interface_theme"

ADDON_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
THEMES_JSON = os.path.join(ADDON_PATH, "resources", "theme_definitions.json")

# identifier used for blender's own built-in theme, not one of ours from themes.json
DEFAULT_THEME_ID = "blender_dark"


def load_theme_definitions():
    """Read themes.json, returns {theme_name: absolute_path}."""
    with open(THEMES_JSON, "r") as f:
        data = json.load(f)

    base_path = os.path.join(ADDON_PATH, data["base_path"])
    return {
        theme_name: os.path.join(base_path, theme_filename)
        for theme_name, theme_filename in data["themes"].items()
    }


def get_theme_path(name):
    """Look up a theme's absolute path by the name it has in themes.json."""
    return load_theme_definitions().get(name)


def list_themes():
    """Return the names of every theme registered in themes.json."""
    return list(load_theme_definitions().keys())


def get_theme_presets_dir(create=True):
    """Return the folder blender looks in for interface theme presets."""
    return bpy.utils.user_resource("SCRIPTS", path=os.path.join("presets", THEME_PRESET_SUBDIR), create=create)


def apply_theme(filepath):
    """Apply a theme .xml file directly, without installing it.

    Args:
        filepath (str): Path to a theme .xml file.

    Returns:
        bool: True if the theme was applied.
    """
    filepath = os.path.abspath(filepath)
    if not os.path.exists(filepath):
        print(f"Could not apply theme, file not found: {filepath}")
        return False

    try:
        bpy.ops.script.execute_preset(filepath=filepath, menu_idname=THEME_PRESET_MENU)
    except RuntimeError as error:
        print(f"Could not apply theme {filepath}: {error}")
        return False

    return True


def install_theme(filepath, overwrite=True):
    """Copy a theme .xml file into blender's user theme presets folder.

    Installing (rather than applying directly) makes the theme show up in
    Preferences > Themes > Presets afterwards.

    Args:
        filepath (str): Path to a theme .xml file to install.
        overwrite (bool): Replace an existing preset of the same name.

    Returns:
        str or None: The installed file path, or None if installation failed.
    """
    filepath = os.path.abspath(filepath)
    if not os.path.exists(filepath):
        print(f"Could not install theme, file not found: {filepath}")
        return None

    presets_dir = get_theme_presets_dir(create=True)
    installed_path = os.path.join(presets_dir, os.path.basename(filepath))

    if os.path.exists(installed_path) and not overwrite:
        return installed_path

    shutil.copyfile(filepath, installed_path)
    return installed_path


def install_and_apply_theme(filepath, overwrite=True):
    """Install a theme .xml file and immediately apply it.

    Args:
        filepath (str): Path to a theme .xml file.
        overwrite (bool): Replace an existing preset of the same name.

    Returns:
        bool: True if the theme was installed and applied.
    """
    installed_path = install_theme(filepath, overwrite=overwrite)
    if installed_path is None:
        return False

    return apply_theme(installed_path)


def apply_default_theme():
    """Reset blender back to its own built-in default (dark) theme."""
    try:
        bpy.ops.preferences.reset_default_theme()
    except RuntimeError as error:
        print(f"Could not reset to the default theme: {error}")
        return False

    return True


def apply_named_theme(name):
    """Apply a theme by name: DEFAULT_THEME_ID, or one from themes.json."""
    if name == DEFAULT_THEME_ID:
        return apply_default_theme()

    filepath = get_theme_path(name)
    if filepath is None:
        print(f"Could not apply theme, unknown theme name: {name}")
        return False

    return apply_theme(filepath)
