import json
import os

import bpy
import bpy.utils.previews

ADDON_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ICONS_JSON = os.path.join(ADDON_PATH, "resources", "icon_definitions.json")

preview_collections = {}


def load_icon_definitions():
    """Read icons.json, returns {icon_name: absolute_path}."""
    with open(ICONS_JSON, "r") as f:
        data = json.load(f)

    base_path = os.path.join(ADDON_PATH, data["base_path"])
    return {
        icon_name: os.path.join(base_path, icon_filename)
        for icon_name, icon_filename in data["icons"].items()
    }


def extract_pcoll():
    """Create a preview collection and load every icon from icons.json into it."""
    pcoll = bpy.utils.previews.new()

    for icon_name, icon_path in load_icon_definitions().items():
        if not os.path.exists(icon_path):
            print(f"Warning: Icon not found at {icon_path}")
            continue

        pcoll.load(icon_name, icon_path, "IMAGE")

    return pcoll


def get_icons_pcoll():
    return preview_collections["ui_icons"]


def get_icon_id(name):
    """Return the icon_id for a registered icon, for use with icon_value."""
    return get_icons_pcoll()[name].icon_id


def register_icons():
    preview_collections["ui_icons"] = extract_pcoll()


def unregister_icons():
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()
