"""Where the builder finds things on disk."""

import os
import sys

from ..utils import base_builder_utils

ADDON_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

# The high resolution library. One .blend per object id, each holding exactly
# one mesh object with the real game materials and textures on it.
# Textures are referenced relatively from assets/ into textures/, so the two
# have to stay siblings.
HIGH_RES_PATH = os.path.join(ADDON_PATH, "asset_browser", "assets")

# The old fbx proxy library, one folder per category. Charon Forge doesn't ship
# one - models/ is an empty placeholder so the catalog still has somewhere to
# look, and every part is served from HIGH_RES_PATH instead (or, for the
# "Simple Proxies" switch, from get_host_model_path() below).
MODEL_PATH = os.path.join(ADDON_PATH, "models")

USER_PATH = os.path.join(os.path.expanduser("~"), "CharonForge")
MODS_PATH = os.path.join(USER_PATH, "mods")
PRESET_PATH = os.path.join(USER_PATH, "presets")


def get_host_model_path():
    """The base builder addon's fbx model folder, or None when it isn't loaded.

    MODEL_PATH above is an empty placeholder, so on its own the "Simple
    Proxies" switch has nothing to switch a part down to. That addon ships the
    whole fbx library and is already a hard requirement of ours, so its copy is
    what the proxies are served from. Laid out the same way MODEL_PATH is -
    one folder per category, one fbx per object id.
    """
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
