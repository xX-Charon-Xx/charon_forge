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
  - Fossils: its override table builds every FOS_ id with its own classes,
    which import the fbx. Ours go into that table ahead of them, so fossils
    come out of the high res library - see objects/fossil.py.

Blender doesn't promise which addon registers first, so when the base builder
addon isn't loaded yet the install is retried on a timer for a few seconds.

Charon Forge doesn't need that addon to work (base_builder_utils falls back
to its own copies of the helpers it borrows). If the addon is installed or
enabled later, or reloaded and drops our hooks, the next thing of ours that
looks it up hooks into it again - see ensure_installed.
"""

import time

import bpy

from . import builder, host_patches, materials
from .objects import fossil
from .utils import base_builder_utils

# Turn either half off here if it ever needs to be taken back out.
INSTALL_BUILDER = True
INSTALL_MATERIALS = True
INSTALL_PATCHES = True
INSTALL_FOSSILS = True

# How long to keep looking for the other addon while blender starts up.
RETRY_SECONDS = 1.0
RETRY_LIMIT = 15

_wanted = False
_installed = False
_attempts = 0

# what install() last handed over, so ensure_installed can tell whether the
# addon still has them
_host_builder = None
_host_provider = None

# ensure_installed runs on every lookup of the addon, which can be thousands
# of times in a bulk build; once the hooks are confirmed in place it only
# looks again after this many seconds
VERIFY_INTERVAL = 1.0
_verified_at = 0.0
_ensuring = False


def is_installed():
    return _installed


def install(retry=True):
    """Hand our builder and materials to the base builder addon.

    Args:
        retry (bool): Keep trying on a timer while that addon isn't loaded yet.

    Returns:
        bool: True once both requested hooks are in place.
    """
    global _wanted, _installed, _attempts, _host_builder, _host_provider
    _wanted = True
    base_builder_utils.set_on_addon_found(ensure_installed)

    # our own override table is the one read while the addon isn't there, so
    # the fossil classes go into it whether or not the addon is found
    fossils_installed = fossil.install() if INSTALL_FOSSILS else True

    if not base_builder_utils.is_available():
        if retry:
            _schedule_retry()
        return False

    installed = fossils_installed

    if INSTALL_MATERIALS:
        provider = materials.create_host_material_provider()
        installed &= provider is not None and base_builder_utils.set_material_provider(provider)
        _host_provider = provider

    if INSTALL_BUILDER:
        host_builder = builder.create_host_builder()
        installed &= host_builder is not None and base_builder_utils.set_builder(host_builder)
        _host_builder = host_builder

    # not counted towards `installed` - a colour path that can't be wrapped
    # only means that tool keeps the addon's own behaviour
    if INSTALL_PATCHES and INSTALL_MATERIALS:
        host_patches.install()

    _installed = installed
    _attempts = 0
    if installed:
        print("Charon Forge: hooked into the base builder addon")
    return installed


def ensure_installed():
    """Hook into the addon now if it has appeared, or lost our hooks, since
    install() last ran.

    base_builder_utils calls this whenever one of its lookups finds the
    addon, so Charon Forge hooks into an addon installed after it the next
    time anything reaches for it, with no restart.

    Returns:
        bool: True when the hooks are in place.
    """
    global _installed, _verified_at, _ensuring
    if not _wanted or _ensuring:
        return _installed

    # checked at most once a second, whether the last check found the hooks
    # in place or failed to install them - a failing install is not retried
    # on every lookup
    now = time.monotonic()
    if now - _verified_at < VERIFY_INTERVAL:
        return _installed
    _verified_at = now

    # install() and the checks below look the addon up again, which calls
    # back in here
    _ensuring = True
    try:
        if _installed and _hooks_still_ours():
            return True
        # our timer is still trying, leave it to that
        if bpy.app.timers.is_registered(_retry):
            return False
        _installed = False
        return install(retry=False)
    finally:
        _ensuring = False


def _hooks_still_ours():
    """False once the addon has been reloaded or reset and dropped ours."""
    if INSTALL_BUILDER and base_builder_utils.get_builder() is not _host_builder:
        return False
    if INSTALL_MATERIALS and base_builder_utils.get_material_provider() is not _host_provider:
        return False
    if INSTALL_FOSSILS and not fossil.is_installed():
        return False
    return True


def remove():
    """Give the base builder addon its own builder and materials back."""
    global _wanted, _installed, _attempts, _host_builder, _host_provider
    _wanted = False
    _attempts = 0
    base_builder_utils.set_on_addon_found(None)

    host_patches.remove()
    fossil.remove()
    if _installed and base_builder_utils.is_available():
        base_builder_utils.reset_all()
    _installed = False
    _host_builder = None
    _host_provider = None


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
            "Charon Forge: base builder addon not found, working on its own - "
            "it will be hooked into once it is installed"
        )
        return None
    return RETRY_SECONDS
