"""Where the builder finds things on disk."""

import os
import sys

from ..utils import base_builder_utils

ADDON_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

# The high res library: one .blend per object id. Its textures are referenced
# relatively into textures/, so the two folders must stay siblings.
HIGH_RES_PATH = os.path.join(ADDON_PATH, "asset_browser", "assets")

# The old fbx proxy library, an empty placeholder: parts come from HIGH_RES_PATH,
# or for "Simple Proxies" from get_host_model_path().
MODEL_PATH = os.path.join(ADDON_PATH, "models")

USER_PATH = os.path.join(os.path.expanduser("~"), "CharonForge")
MODS_PATH = os.path.join(USER_PATH, "mods")

# Presets are shared with the base builder addon's folder, so both list the same ones.
HOST_USER_PATH = os.path.join(os.path.expanduser("~"), "NoMansSkyBaseBuilder")
PRESET_PATH = os.path.join(HOST_USER_PATH, "presets")


def get_host_model_path():
    """The base builder addon's fbx model folder, or None when it isn't loaded.
    Serves the "Simple Proxies" switch, since MODEL_PATH is empty."""
    addon_module = base_builder_utils.get_addon_module_name()
    if addon_module is None:
        return None

    # its own paths module knows where it put them, when it has been imported
    host_paths = sys.modules.get("%s.builder.paths" % addon_module)
    model_path = getattr(host_paths, "MODEL_PATH", None)

    if model_path is None:
        addon = sys.modules.get(addon_module)
        addon_file = getattr(addon, "__file__", None)
        if addon_file is None:
            return None
        model_path = os.path.join(os.path.dirname(addon_file), "models")

    return model_path if os.path.isdir(model_path) else None
