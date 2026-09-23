"""Installing Charon Forge's builder and materials into the base builder addon.

That addon has two hooks - set_builder() and set_material_provider() - and this
is what actually hands ours over, so its own panels and operators work on
Charon Forge's high res parts:

  - Materials: its Colour panel calls material.assign_material(), which goes to
    whichever provider is active. The default one paints a flat material into
    slot 0, which does nothing visible to a high res part: the colour those
    read is on the object (nms_p/s/t/q), and Solid shading is showing
    object.color. Ours repaints those instead - see materials/mixin.py.
  - Builder: its tools place parts through get_builder().add_part(), so ours
    puts the high res model there where the library has one.
  - Colour paths that go around the material hook (groups, curve followers)
    are wrapped in host_patches.py, so they colour high res parts too.

Blender doesn't promise which addon registers first, so when the base builder
addon isn't loaded yet the install is retried on a timer for a few seconds.
"""

import bpy

from . import builder, host_patches, materials
from .utils import base_builder_utils

# Turn either half off here if it ever needs to be taken back out.
INSTALL_BUILDER = True
INSTALL_MATERIALS = True
INSTALL_PATCHES = True

# How long to keep looking for the other addon while blender starts up.
RETRY_SECONDS = 1.0
RETRY_LIMIT = 15

_wanted = False
_installed = False
_attempts = 0


def is_installed():
    return _installed


def install(retry=True):
    """Hand our builder and materials to the base builder addon.

    Args:
        retry (bool): Keep trying on a timer while that addon isn't loaded yet.

    Returns:
        bool: True once both requested hooks are in place.
    """
    global _wanted, _installed, _attempts
    _wanted = True

    if not base_builder_utils.is_available():
        if retry:
            _schedule_retry()
        return False

    installed = True

    if INSTALL_MATERIALS:
        provider = materials.create_host_material_provider()
        installed &= provider is not None and base_builder_utils.set_material_provider(provider)

    if INSTALL_BUILDER:
        host_builder = builder.create_host_builder()
        installed &= host_builder is not None and base_builder_utils.set_builder(host_builder)

    # not counted towards `installed` - a colour path that can't be wrapped
    # only means that tool keeps the addon's own behaviour
    if INSTALL_PATCHES and INSTALL_MATERIALS:
        host_patches.install()

    _installed = installed
    _attempts = 0
    if installed:
        print("Charon Forge: hooked into the base builder addon")
    return installed


def remove():
    """Give the base builder addon its own builder and materials back."""
    global _wanted, _installed, _attempts
    _wanted = False
    _attempts = 0

    host_patches.remove()
    if _installed and base_builder_utils.is_available():
        base_builder_utils.reset_all()
    _installed = False


def _schedule_retry():
    if bpy.app.timers.is_registered(_retry):
        return
    bpy.app.timers.register(_retry, first_interval=RETRY_SECONDS)


def _retry():
    """Try again while blender is still bringing addons up.

    Returns:
        float: Seconds until the next attempt, or None to stop.
    """
    global _attempts

    # unregistered while we were waiting
    if not _wanted:
        return None

    _attempts += 1
    if install(retry=False):
        return None

    if _attempts >= RETRY_LIMIT:
        print(
            "Charon Forge: base builder addon not found, "
            "its panels will not colour or build Charon Forge parts"
        )
        return None
    return RETRY_SECONDS
