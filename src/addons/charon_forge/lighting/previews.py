"""Preview swatches for the sky pickers, drawn from the game's own colours.

    planet  the entry's gradient as the camera sees it - SkyUpper at the top,
            Sky, Horizon, and the fog below - with its sun disc
    space   a window onto the game's nebula dome, tinted exactly as the sky
            shader tints it (R -> NebulaColour3, G -> 1, B -> 2) over the
            entry's Bottom / Mid / Top gradient

Made in memory (bpy.utils.previews, pixels written directly), once per entry
per session; nothing is written to disk.
"""

import os

import bpy
import bpy.utils.previews
import numpy as np

from . import data

SIZE = 96
_collection = None
_dome = None


def _previews():
    global _collection
    if _collection is None:
        _collection = bpy.utils.previews.new()
    return _collection


def unregister():
    global _collection, _dome
    if _collection is not None:
        bpy.utils.previews.remove(_collection)
    _collection = None
    _dome = None


def _put(key, rgb):
    """rgb: SIZE x SIZE x 3 display values, rows top to bottom."""
    previews = _previews()
    if key in previews:
        return previews[key].icon_id
    preview = previews.new(key)
    preview.image_size = (SIZE, SIZE)
    rgba = np.ones((SIZE, SIZE, 4), np.float32)
    rgba[..., :3] = np.clip(rgb, 0.0, 1.0)
    preview.image_pixels_float = rgba[::-1].ravel()     # Blender's rows go up
    return preview.icon_id


def _colour(entry, key, default=(0.0, 0.0, 0.0)):
    return np.array(entry.get(key, default), np.float32)[:3]


def _ramp(t, stops):
    """Colour at t (array) along [(position, colour), ...]."""
    positions = [p for p, _ in stops]
    return np.stack([np.interp(t, positions, [c[i] for _, c in stops])
                     for i in range(3)], -1)


def planet_icon(kind, list_name, index):
    key = "planet:%s:%s:%d" % (kind, list_name, index)
    if key in _previews():
        return _previews()[key].icon_id
    entry = data.planet_entry(kind, list_name, index)
    horizon_at = 0.66
    t = (np.arange(SIZE) + 0.5) / SIZE
    column = _ramp(t, [(0.0, _colour(entry, "SkyUpperColour")),
                       (0.45, _colour(entry, "SkyColour")),
                       (horizon_at, _colour(entry, "HorizonColour")),
                       (horizon_at + 0.07, _colour(entry, "FogColour") * 0.6),
                       (1.0, _colour(entry, "FogColour") * 0.5)])
    rgb = np.repeat(column[:, None, :], SIZE, 1)
    # the sun, where a camera looking up at the sky would see it
    y, x = np.mgrid[0:SIZE, 0:SIZE]
    d = np.hypot(x - SIZE * 0.72, y - SIZE * 0.3) / (SIZE * 0.07)
    glow = np.where(d < 1.0, 1.0, np.clip(1.0 - (d - 1.0) / 2.0, 0.0, 1.0) ** 2 * 0.6)
    sun = _colour(entry, "SunColour", (1.0, 1.0, 1.0))
    rgb = rgb + (sun - rgb) * glow[..., None]
    return _put(key, rgb)


def _dome_window():
    """A SIZE x SIZE window of the nebula dome's three masks, 0..1, from its
    busiest band."""
    global _dome
    if _dome is not None:
        return _dome
    path = data.spacedome_path()
    _dome = np.zeros((SIZE, SIZE, 3), np.float32)
    if not path or not os.path.exists(path):
        return _dome
    image = bpy.data.images.load(path, check_existing=True)
    w, h = image.size
    pixels = np.empty(w * h * 4, np.float32)
    image.pixels.foreach_get(pixels)
    pixels = pixels.reshape(h, w, 4)[::-1, :, :3]          # rows top down
    ys = np.linspace(h * 0.30, h * 0.68, SIZE).astype(int)
    xs = np.linspace(w * 0.30, w * 0.68, SIZE).astype(int)
    _dome = pixels[np.ix_(ys, xs)]
    return _dome


def space_icon(sky_key):
    key = "space:" + sky_key
    if key in _previews():
        return _previews()[key].icon_id
    entry = data.space_entry_by_key(sky_key)
    t = (np.arange(SIZE) + 0.5) / SIZE
    column = _ramp(t, [(0.0, _colour(entry, "TopColour")),
                       (0.5, _colour(entry, "MidColour")),
                       (1.0, _colour(entry, "BottomColour"))]) * 0.25
    dome = _dome_window()
    rgb = (column[:, None, :]
           + dome[..., 0:1] * _colour(entry, "NebulaColour3")
           + dome[..., 1:2] * _colour(entry, "NebulaColour1")
           + dome[..., 2:3] * _colour(entry, "NebulaColour2"))
    return _put(key, rgb)
