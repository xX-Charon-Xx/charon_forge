"""Packing the library's textures into the .blend when it is saved.

A part's images only point at the PNGs in this addon's install
(asset_browser/textures). A .blend shared with someone else then shows them
pink - the path is to a folder on the sender's machine. Packed, the texture
data travels inside the .blend and the file opens correctly anywhere, with or
without Charon Forge.

Only images from the library are packed; anything else in the file is left
as the user has it. Each image is packed once - an image already packed is
skipped, so after the first save only textures new since the last one cost
anything. The addon preference pack_textures_on_save turns it off.
"""

import os

import bpy

from .paths import ADDON_PATH, TEXTURES_PATH

# the space station's textures, beside its models
STATION_TEXTURES_PATH = os.path.join(ADDON_PATH, "models", "space_station", "textures")


def _library_texture_path(image):
    """The file a library image points at, or None if it is not one of ours."""
    if image.source != "FILE" or not image.filepath:
        return None
    path = os.path.normcase(os.path.abspath(
        bpy.path.abspath(image.filepath, library=image.library)
    ))
    textures = os.path.normcase(os.path.abspath(TEXTURES_PATH))
    try:
        inside = os.path.commonpath([path, textures]) == textures
    except ValueError:
        # different drives on Windows
        inside = False
    return path if inside else None


def pack_library_textures():
    """Pack every library image not packed yet.

    Returns:
        (int, int): images packed, and images whose file could not be found
            or read (left unpacked).
    """
    packed = failed = 0
    for image in bpy.data.images:
        if image.packed_file is not None or image.library is not None:
            continue
        # nothing draws it - e.g. a variant samplers.py repointed away from
        if image.users == 0:
            continue
        path = _library_texture_path(image)
        if path is None:
            continue
        if not os.path.isfile(path):
            failed += 1
            continue
        try:
            image.pack()
            packed += 1
        except RuntimeError as error:
            print("Charon Forge: could not pack %s: %s" % (image.name, error))
            failed += 1
    return packed, failed


def relink_library_textures():
    """Point every image whose file is missing at the same texture in this
    install's library, by file name, and reload it.

    What a .blend opened on another machine (or after the addon moved)
    needs: its images still name the textures, but by a path to a folder
    that is not there. Packed images and images from linked libraries are
    left alone - they have their data already, or are not this file's.

    Returns:
        (int, int): images relinked, and images still missing because the
            library has no texture of that name.
    """
    if not os.path.isdir(TEXTURES_PATH):
        return 0, 0
    by_name = {name.lower(): os.path.join(TEXTURES_PATH, name)
               for name in os.listdir(TEXTURES_PATH)}

    relinked = missing = 0
    for image in bpy.data.images:
        if image.source != "FILE" or not image.filepath:
            continue
        if image.packed_file is not None or image.library is not None:
            continue
        current = bpy.path.abspath(image.filepath)
        if os.path.isfile(current):
            continue
        # a path saved on Windows keeps its backslashes on any machine
        name = image.filepath.replace("\\", "/").rsplit("/", 1)[-1].lower()
        replacement = by_name.get(name)
        if replacement is None:
            missing += 1
            continue
        image.filepath = replacement
        image.reload()
        relinked += 1
    return relinked, missing


def reload_library_textures():
    """Read every texture that comes from this install again, as it is on
    disk now - the parts' (asset_browser/textures) and the space station's
    (models/space_station/textures).

    A packed texture holds the pixels it had when it was packed, so one whose
    file is here is unpacked back onto that file first; saving packs it
    again, fresh (see pack_library_textures). Anything else in the file - the
    user's own images, linked ones - is left alone.

    Returns:
        int: Textures reloaded.
    """
    folders = [TEXTURES_PATH, STATION_TEXTURES_PATH]
    by_name = {}
    for folder in folders:
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                by_name.setdefault(name.lower(), os.path.join(folder, name))

    reloaded = 0
    for image in bpy.data.images:
        if image.source != "FILE" or not image.filepath or image.library is not None:
            continue
        name = image.filepath.replace("\\", "/").rsplit("/", 1)[-1].lower()
        path = by_name.get(name)
        if path is None:
            continue
        try:
            if bpy.path.abspath(image.filepath) != path:
                image.filepath = path
            if image.packed_file is not None:
                image.unpack(method="USE_ORIGINAL")
            image.reload()
            reloaded += 1
        except RuntimeError as error:
            print("Charon Forge: could not reload %s: %s" % (image.name, error))
    return reloaded


def _pack_on_save_enabled():
    from ..addon_preferences import get_addon_preferences

    prefs = get_addon_preferences()
    return prefs is None or getattr(prefs, "pack_textures_on_save", True)


@bpy.app.handlers.persistent
def _on_save_pre(_filepath=None):
    if not _pack_on_save_enabled():
        return
    try:
        packed, failed = pack_library_textures()
    except Exception as error:                            # noqa: BLE001
        print("Charon Forge: could not pack textures: %r" % error)
        return
    if packed or failed:
        print("Charon Forge: packed %d texture(s) into the file%s"
              % (packed, ", %d missing" % failed if failed else ""))


def register():
    if _on_save_pre not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(_on_save_pre)


def unregister():
    if _on_save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_on_save_pre)
