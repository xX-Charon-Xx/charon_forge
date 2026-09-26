"""Access to the installed No Man's Sky Base Builder addon's hooks.

That addon exposes two hooks from its `builder` subpackage:

    set_builder(MyBuilder())             # MyBuilder subclasses its Builder
    set_material_provider(MyMaterials()) # MyMaterials subclasses its MaterialProvider

Passing None to either restores the addon's own logic. Both check the type of
what they are given, so our classes have to subclass the addon's own Builder
and MaterialProvider - get_builder_class() and get_material_provider_class()
hand those out, since they only exist once that addon is loaded.

Nothing here imports the addon itself. It has to be enabled already - these
look it up among the loaded modules and report None/False when it is not
there, so call them after both addons are registered rather than at import
time. A disable/enable or reload of that addon re-imports it, which drops
whatever we set; apply ours again afterwards.
"""

import importlib
import sys

import bpy

# The names the addon is installed under, most wanted first. Blender names an
# extension's module after where it came from as well as its folder -
# bl_ext.user_default.<folder> installed from disk, bl_ext.blender_org.<folder>
# from the online platform, the bare folder for a legacy addon - so only the
# last part is matched. The release is installed as its extension id; the
# development copy was linked in as official_nms_builder.
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
    """The enabled addon to hook into: one installed under a known name
    first, then any other exposing the same hooks - so a reinstall under a
    different folder, or from a different repository, still works."""
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

    Called for every part placed, so the last answer is reused for as long
    as that addon is still enabled and loaded, and only a miss scans the
    enabled addons again.
    """
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


# Called whenever a lookup finds the addon - hooks.py sets it, so an addon
# that was installed or enabled after Charon Forge is hooked into by the
# next thing that reaches for it. See hooks.ensure_installed.
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
#
# Charon Forge has no fbx/scene-plumbing utilities or part-override classes of
# its own any more - it uses the base builder addon's, in place, rather than
# keeping a second copy to maintain. blend_utils/overrides below are used
# exactly like an ordinary imported module (blend_utils.add_to_scene(...)),
# but every attribute access resolves against the real module at call time
# instead of once at import time - so Charon Forge still loads even if the
# base builder addon happens to register after it, and a disable/enable or
# reload of that addon is picked up on the next call rather than needing
# these re-imported.


def get_module(relative_path):
    """A submodule of the host addon, e.g. "utils.blend_utils", if it is loaded.

    Nothing here imports the addon - see the module docstring - so this only
    succeeds once something inside that addon has already imported the
    submodule itself, which every submodule of it has by the time the addon
    finishes registering.
    """
    addon_module = get_addon_module_name()
    if addon_module is None:
        return None
    return sys.modules.get(f"{addon_module}.{relative_path}")


class _HostModuleProxy:
    """Stands in for a host addon submodule, resolved on every attribute access.

    `blend_utils = _HostModuleProxy("utils.blend_utils", fallback="blend_utils")` then
    `blend_utils.add_to_scene(...)` behaves like the module was imported
    directly, except the lookup happens now rather than at import time.

    With a `fallback` (a module in utils/fallbacks), calls go there while
    the host addon is not installed, so Charon Forge works on its own, and
    switch to the host's module as soon as it is.
    """

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


# The host addon's utils.blend_utils - add_to_scene, select, and so on.
# Every part placed goes through add_to_scene, so without a fallback nothing
# could be placed - the asset browser included - while the addon is missing.
blend_utils = _HostModuleProxy("utils.blend_utils", fallback="blend_utils")

# The host addon's builder.overrides - which Part subclass builds which id.
# Exposes get_part_class(object_id)/get_override_class(object_id) to look one
# up, and register_override(class_ref, object_ids)/unregister_override(ids) to
# add or remove entries - the extension point another addon's own part
# classes are meant to go through, ahead of the built in table.
overrides = _HostModuleProxy("builder.overrides", fallback="overrides")

# The host addon's utils.userdata - packing/unpacking a UserData bitfield.
userdata = _HostModuleProxy("utils.userdata", fallback="userdata")

# The host addon's utils.python - load_dictionary, get_adjacent_dict_key,
# prefer_int. Plain python helpers, nothing addon specific about them.
python_utils = _HostModuleProxy("utils.python", fallback="python")

# The host addon's tools.batch_tool - BatchTool, the class behind
# scene.nms_batch_tool. The host addon registers that scene pointer itself,
# so Charon Forge has no BatchTool of its own any more - see get_batch_tool().
batch_tool_module = _HostModuleProxy("tools.batch_tool")

# The host addon's save_editor.save_editor_utils - reading and writing the
# player's NMS save files. save_base_to_save_file below is what actually
# writes, backups and atomic replace included.
save_editor_utils = _HostModuleProxy("save_editor.save_editor_utils")

# The host addon's utils.material - BAKED_PALETTES_UI (the material_switch
# enum items) and get_colours_from_palette(palette).
material = _HostModuleProxy("utils.material")


def get_colour_preview_collection():
    """The host addon's bpy.utils.previews collection of colour swatch icons.

    Built at the host's own register() from its images/colours folder and
    kept on its top level __init__ module rather than a submodule, so this
    reaches into sys.modules for that module directly instead of going
    through _HostModuleProxy (which only resolves dotted submodules). None
    if the host addon is not loaded or has not registered yet.
    """
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

    Holds nms_account_selected/nms_save_slot - the Account/Save Slot
    dropdowns - and the corvettes read from the chosen slot. Charon Forge's
    own copy of the save editor (save_editor/), so the Helmsman panel works
    without the base builder addon.
    """
    scene = bpy.context.scene
    return getattr(scene, "charon_save_data", None)


def get_save_corvettes():
    """The corvettes in the selected save slot, or [].

    BaseData objects - base_index, base_name, user_data, parts_count - as
    extracted by the host addon's save_editor_utils.extract_bases_list_from_save
    and already sorted by user_data, which is the corvette's position in the
    player's ship slots. Populated when a save slot is picked, so this only
    has anything once that has happened.
    """
    save_data = get_save_data()
    if save_data is None:
        return []

    extracted = getattr(type(save_data), "extracted_base_data", None)
    if not extracted:
        return []
    return extracted.get("corvettes") or []


def get_current_save_links():
    """The save file paths for the selected save slot, or None.

    What save_base_to_save_file calls save_slot - a slot holds more than one
    file and it works out which is newest itself.
    """
    save_data = get_save_data()
    if save_data is None:
        return None

    slot_data = save_data.get_current_slot_data()
    return slot_data["saves"] if slot_data else None


def write_objects_to_corvettes(ships, save_links):
    """Replace several corvettes' parts in the save file, in one go.

    Straight through to save_editor_utils.save_bases_to_save_file (Charon
    Forge's own copy): each save file is read, updated with every ship,
    backed up and written once, however many ships there are, and rolled
    back if a later write fails.

    Args:
        ships (list): (objects_data, corvette) pairs - parts English keyed as
            they come in a ship batch (see helmsman_utils), and the BaseData
            to overwrite (see get_save_corvettes).
        save_links: the slot's save paths - see get_current_save_links.

    Returns:
        (list, dict, str): indices into `ships` that were written, {index:
            reason} for those that were not, and a message for the user.
    """
    from ..save_editor import save_editor_utils as charon_save_editor_utils

    return charon_save_editor_utils.save_bases_to_save_file(
        [(objects_data, corvette, None) for objects_data, corvette in ships],
        save_links,
    )


def get_host_save_folder_path():
    """The NMS save folder the host addon's save manager is pointed at.

    Read straight off its addon_preferences module rather than
    scene/AddonPreferences state of our own, so this always agrees with
    whatever the user picked (or the host's own OS specific default) over
    there - see save_editor/save_editor_utils.get_default_save_folder in
    that addon. None if it is not loaded.
    """
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
    """Make the addon use our builder.

    Args:
        builder_object: An instance of a get_builder_class() subclass, or None
            to restore the addon's own builder.

    Returns:
        bool: True if the addon took it.
    """
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
    """Make the addon use our material logic.

    Args:
        provider: An instance of a get_material_provider_class() subclass, or
            None to restore the addon's own material logic.

    Returns:
        bool: True if the addon took it.
    """
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
