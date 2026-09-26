import json
import os

import bpy
import bpy.utils.previews

ADDON_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ICONS_JSON = os.path.join(ADDON_PATH, "resources", "icon_definitions.json")

# One PNG per object id, named <object_id>.png - the asset browser's per-part
# thumbnails, scanned rather than listed in icon_definitions.json since there
# are thousands of them.
ASSET_ICONS_PATH = os.path.join(ADDON_PATH, "asset_browser", "icons")

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


# icons already reported missing, so the console isn't flooded from draw code
_missing_icons = set()


def get_icon_id(name):
    """Return the icon_id for a registered icon, for use with icon_value.

    0 - no icon - when it isn't there: its image is missing from images/ or
    the icons aren't loaded. Panels call this from draw code, where raising
    would leave the whole panel blank.
    """
    pcoll = preview_collections.get("ui_icons")
    if pcoll is not None and name in pcoll:
        return pcoll[name].icon_id
    if name not in _missing_icons:
        _missing_icons.add(name)
        print(f"Charon Forge: icon {name!r} is not loaded - check resources/icon_definitions.json")
    return 0


def load_asset_icons():
    """Scan ASSET_ICONS_PATH for PNGs and load them into a preview collection.

    One icon per object id, named <object_id>.png - what the asset browser's
    grid looks each part up by.
    """
    pcoll = bpy.utils.previews.new()

    if not os.path.exists(ASSET_ICONS_PATH):
        print(f"Directory not found: {ASSET_ICONS_PATH}")
        return pcoll

    for filename in os.listdir(ASSET_ICONS_PATH):
        if filename.lower().endswith(".png"):
            icon_name = os.path.splitext(filename)[0]
            pcoll.load(icon_name, os.path.join(ASSET_ICONS_PATH, filename), "IMAGE")

    return pcoll


def get_asset_icons_pcoll():
    return preview_collections["asset_icons"]


def register_icons():
    preview_collections["ui_icons"] = extract_pcoll()
    preview_collections["asset_icons"] = load_asset_icons()


def unregister_icons():
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()
