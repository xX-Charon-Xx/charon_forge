"""Access to the base builder addon's set_builder and set_material_provider hooks.
Call after both addons are registered; reloading that addon drops what we set."""

import importlib
import sys

import bpy

# names the addon is installed under, most wanted first; only the last part of the
# module name is matched, since Blender prefixes extensions with where they came from
PREFERRED_ADDON_NAMES = ("no_mans_sky_base_builder", "official_nms_builder")

# how the addon is named to the user, in messages about features that need it
HOST_ADDON_NAME = "No Man's Sky Base Builder"

# the hooks live here, relative to the addon module
HOOKS_SUBMODULE = "builder"
HOOK_NAMES = ("set_builder", "get_builder", "set_material_provider", "get_material_provider")


def _hooks_module_for(addon_module):
    module = sys.modules.get(f"{addon_module}.{HOOKS_SUBMODULE}")
    if module is not None and all(hasattr(module, name) for name in HOOK_NAMES):
        return module
    return None


# what the last lookup found, checked again before it is trusted
_found_module = None


def _find_addon_module(enabled):
    """The enabled addon to hook into: a known name first, then any other with the same hooks."""
    for name in PREFERRED_ADDON_NAMES:
        for addon_module in enabled:
            if addon_module.rsplit(".", 1)[-1] == name and _hooks_module_for(addon_module):
                return addon_module
    for addon_module in enabled:
        if _hooks_module_for(addon_module):
            return addon_module
    return None


def get_addon_module_name():
    """Module name of the enabled base builder addon that has the hooks, or None.
    The last answer is reused while that addon stays loaded."""
    global _found_module
    enabled = bpy.context.preferences.addons.keys()

    found = _found_module
    if found is None or found not in enabled or _hooks_module_for(found) is None:
        found = _find_addon_module(enabled)
        if found != _found_module and found is not None:
            print(f"Charon Forge: using the base builder addon installed as {found}")
        _found_module = found

    if found is not None and _on_addon_found is not None:
        _on_addon_found()
    return found


# called whenever a lookup finds the addon (hooks.py sets it), so an addon enabled later
# is hooked by the next lookup - see hooks.ensure_installed
_on_addon_found = None


def set_on_addon_found(callback):
    global _on_addon_found
    _on_addon_found = callback


def get_hooks_module():
    """The addon's `builder` subpackage holding the hooks, or None."""
    addon_module = get_addon_module_name()
    return _hooks_module_for(addon_module) if addon_module else None


def is_available():
    return get_hooks_module() is not None


def missing_host_message(feature):
    """What to tell the user when `feature` needs the base builder addon and
    it isn't enabled."""
    return (
        f"{feature} needs the {HOST_ADDON_NAME} addon - install and enable it "
        "in Preferences > Add-ons to use this"
    )


# --- other submodules --------------------------------------------------------
# the host's modules, looked up on every call so its load order and reloads don't matter


def get_module(relative_path):
    """A submodule of the host addon by dotted name, if it is already loaded."""
    addon_module = get_addon_module_name()
    if addon_module is None:
        return None
    return sys.modules.get(f"{addon_module}.{relative_path}")


class _HostModuleProxy:
    """Stands in for a host addon submodule, resolved on every attribute access.
    With a `fallback` (utils/fallbacks), calls go there while the host addon is missing."""

    def __init__(self, relative_path, fallback=None):
        self._relative_path = relative_path
        self._fallback = fallback

    def __getattr__(self, name):
        module = get_module(self._relative_path)
        if module is None and self._fallback is not None:
            module = importlib.import_module(f".fallbacks.{self._fallback}", __package__)
        if module is None:
            raise AttributeError(
                f"{self._relative_path} has no attribute {name!r} "
                "(base builder addon not loaded)"
            )
        return getattr(module, name)


# The host addon's utils.blend_utils; every part placed goes through add_to_scene,
# so the fallback keeps placing working without the addon
blend_utils = _HostModuleProxy("utils.blend_utils", fallback="blend_utils")

# The host addon's builder.overrides - which Part subclass builds which id, and where
# other addons register their own part classes (register_override)
overrides = _HostModuleProxy("builder.overrides", fallback="overrides")

# The host addon's utils.userdata - packing/unpacking a UserData bitfield.
userdata = _HostModuleProxy("utils.userdata", fallback="userdata")

# The host addon's utils.python - load_dictionary, get_adjacent_dict_key,
# prefer_int. Plain python helpers, nothing addon specific about them.
python_utils = _HostModuleProxy("utils.python", fallback="python")

# The host addon's tools.batch_tool - BatchTool, behind scene.nms_batch_tool, which the
# host registers itself (see get_batch_tool())
batch_tool_module = _HostModuleProxy("tools.batch_tool")

# The host addon's save_editor.save_editor_utils - reading and writing NMS save files.
save_editor_utils = _HostModuleProxy("save_editor.save_editor_utils")

# The host addon's utils.material - BAKED_PALETTES_UI (the material_switch
# enum items) and get_colours_from_palette(palette).
material = _HostModuleProxy("utils.material")


def get_colour_preview_collection():
    """The host addon's colour swatch preview collection, or None if it isn't registered.
    Kept on its top level module, so it's read from sys.modules directly."""
    addon_module = get_addon_module_name()
    if addon_module is None:
        return None

    module = sys.modules.get(addon_module)
    if module is None:
        return None

    return getattr(module, "preview_collections", {}).get("main")


def get_batch_tool():
    """The host addon's scene.nms_batch_tool, or None if it is not loaded."""
    scene = bpy.context.scene
    return getattr(scene, "nms_batch_tool", None)


def get_save_data():
    """Charon Forge's own scene.charon_save_data (a CharonSaveManager), or None.
    Holds the Account/Save Slot choice and its corvettes, so Helmsman works without the host."""
    scene = bpy.context.scene
    return getattr(scene, "charon_save_data", None)


def get_save_corvettes():
    """The corvettes (BaseData) in the selected save slot, sorted by ship slot, or [].
    Only filled once a save slot has been picked."""
    save_data = get_save_data()
    if save_data is None:
        return []

    extracted = getattr(type(save_data), "extracted_base_data", None)
    if not extracted:
        return []
    return extracted.get("corvettes") or []


def get_current_save_links():
    """The save file paths for the selected save slot, or None."""
    save_data = get_save_data()
    if save_data is None:
        return None

    slot_data = save_data.get_current_slot_data()
    return slot_data["saves"] if slot_data else None


def write_objects_to_corvettes(ships, save_links):
    """Replace several corvettes' parts in the save file in one go, rolling back on failure.
    Returns (written indices, {index: reason} for the rest, message for the user)."""
    from ..save_editor import save_editor_utils as charon_save_editor_utils

    return charon_save_editor_utils.save_bases_to_save_file(
        [(objects_data, corvette, None) for objects_data, corvette in ships],
        save_links,
    )


def get_host_save_folder_path():
    """The NMS save folder the host addon's save manager points at, or None if not loaded.
    Read off its addon preferences, so it always agrees with what the user picked there."""
    host_addon_preferences = get_module("addon_preferences")
    if host_addon_preferences is None:
        return None
    return host_addon_preferences.get_save_folder_path()


# --- base classes, to subclass ---------------------------------------------

def get_builder_class():
    """The addon's Builder class. Custom builders must subclass it."""
    hooks = get_hooks_module()
    return getattr(hooks, "Builder", None) if hooks else None


def get_material_provider_class():
    """The addon's MaterialProvider class. Custom materials must subclass it."""
    hooks = get_hooks_module()
    return getattr(hooks, "MaterialProvider", None) if hooks else None


# --- builder hook ----------------------------------------------------------

def get_builder():
    """The builder the addon is currently using, or None."""
    hooks = get_hooks_module()
    return hooks.get_builder() if hooks else None


def set_builder(builder_object):
    """Make the addon use our builder, or its own with None. True if it took it."""
    hooks = get_hooks_module()
    if hooks is None:
        print("Charon Forge: base builder addon not found, builder not set")
        return False

    try:
        hooks.set_builder(builder_object)
    except TypeError as error:
        print(f"Charon Forge: could not set builder: {error}")
        return False
    return True


def reset_builder():
    """Put the addon's own builder back."""
    return set_builder(None)


# --- material hook ---------------------------------------------------------

def get_material_provider():
    """The material provider the addon is currently using, or None."""
    hooks = get_hooks_module()
    return hooks.get_material_provider() if hooks else None


def set_material_provider(provider):
    """Make the addon use our material logic, or its own with None. True if it took it."""
    hooks = get_hooks_module()
    if hooks is None:
        print("Charon Forge: base builder addon not found, material provider not set")
        return False

    try:
        hooks.set_material_provider(provider)
    except TypeError as error:
        print(f"Charon Forge: could not set material provider: {error}")
        return False
    return True


def reset_material_provider():
    """Put the addon's own material logic back."""
    return set_material_provider(None)


def reset_all():
    """Undo both hooks - call from our unregister()."""
    reset_builder()
    reset_material_provider()
