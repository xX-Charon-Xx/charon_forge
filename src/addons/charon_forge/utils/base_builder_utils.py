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

import sys

import bpy

# the extension module the addon is installed as on this machine - it is
# linked into extensions/user_default/official_nms_builder
PREFERRED_ADDON_MODULE = "bl_ext.user_default.official_nms_builder"

# the hooks live here, relative to the addon module
HOOKS_SUBMODULE = "builder"
HOOK_NAMES = ("set_builder", "get_builder", "set_material_provider", "get_material_provider")


def _hooks_module_for(addon_module):
    module = sys.modules.get(f"{addon_module}.{HOOKS_SUBMODULE}")
    if module is not None and all(hasattr(module, name) for name in HOOK_NAMES):
        return module
    return None


def get_addon_module_name():
    """Module name of the enabled base builder addon that has the hooks, or None.

    Tries PREFERRED_ADDON_MODULE first, then any other enabled addon exposing
    the same hooks, so a reinstall under a different folder name still works.
    """
    enabled = bpy.context.preferences.addons.keys()

    if PREFERRED_ADDON_MODULE in enabled and _hooks_module_for(PREFERRED_ADDON_MODULE):
        return PREFERRED_ADDON_MODULE

    for addon_module in enabled:
        if _hooks_module_for(addon_module):
            return addon_module
    return None


def get_hooks_module():
    """The addon's `builder` subpackage holding the hooks, or None."""
    addon_module = get_addon_module_name()
    return _hooks_module_for(addon_module) if addon_module else None


def is_available():
    return get_hooks_module() is not None


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
