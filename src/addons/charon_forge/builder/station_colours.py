"""Names and swatch icons for the space station's colour lists.

The game's station palettes have no names of their own (STATION0..35), so
each is named after the colours it is made of - "Grey & Orange" - and shown
with a swatch of them, drawn into a preview icon once and kept.
"""

import colorsys

import bpy
import bpy.utils.previews

_previews = None
SWATCH_SIZE = 32


def register():
    global _previews
    if _previews is None:
        _previews = bpy.utils.previews.new()


def unregister():
    global _previews
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None


def swatch_icon(key, colours):
    """The icon id of a swatch of `colours` (sRGB, 0..1) in side by side
    stripes, drawn the first time it is asked for."""
    if _previews is None:
        return 0
    if key in _previews:
        return _previews[key].icon_id
    preview = _previews.new(key)
    size = SWATCH_SIZE
    stripes = [tuple(colour[:3]) for colour in colours] or [(0.0, 0.0, 0.0)]
    pixels = []
    for _y in range(size):
        for x in range(size):
            r, g, b = stripes[min(x * len(stripes) // size, len(stripes) - 1)]
            pixels += (r, g, b, 1.0)
    preview.image_size = (size, size)
    # a preview's pixels are shown as they are, so sRGB goes straight in
    preview.image_pixels_float = pixels
    return preview.icon_id


def colour_name(colour):
    """A plain name for an sRGB colour: Grey, Dark Blue, Pale Pink..."""
    r, g, b = (min(max(c, 0.0), 1.0) for c in colour[:3])
    hue, saturation, value = colorsys.rgb_to_hsv(r, g, b)
    degrees = hue * 360
    if saturation < 0.06 or value < 0.12:
        if value < 0.18:
            return "Black"
        if value < 0.45:
            return "Dark Grey"
        if value < 0.75:
            return "Grey"
        return "Light Grey" if value < 0.92 else "White"

    # greys with a tint - most station colours are these
    if saturation < 0.2:
        for limit, light, mid, dark in ((50, "Beige", "Taupe", "Dark Taupe"),
                                        (170, "Sage", "Olive Grey", "Dark Olive"),
                                        (250, "Pale Slate", "Slate", "Dark Slate"),
                                        (340, "Lilac", "Mauve", "Plum"),
                                        (361, "Beige", "Taupe", "Dark Taupe")):
            if degrees < limit:
                return light if value > 0.72 else (mid if value > 0.42 else dark)

    for limit, name in ((15, "Red"), (40, "Orange"), (65, "Yellow"), (90, "Lime"),
                        (150, "Green"), (185, "Teal"), (200, "Cyan"), (255, "Blue"),
                        (290, "Purple"), (330, "Magenta"), (345, "Pink"), (361, "Red")):
        if degrees < limit:
            break
    if name in ("Orange", "Yellow") and value < 0.6:
        return "Brown"
    if name == "Red" and saturation < 0.5 and value > 0.7:
        return "Pink"
    if value < 0.4:
        return "Dark " + name
    if saturation < 0.35 and value > 0.8:
        return "Pale " + name
    return name


def colours_name(colours):
    """A name for a set of colours: its first, and whichever of the rest
    stands out from it most - a real colour before another grey, since that
    accent is what tells one palette from the next."""
    first = colour_name(colours[0])

    def saturation(colour):
        r, g, b = (min(max(c, 0.0), 1.0) for c in colour[:3])
        _h, s, v = colorsys.rgb_to_hsv(r, g, b)
        return s if v > 0.25 else 0.0

    def distance(colour):
        return sum((a - b) ** 2 for a, b in zip(colour[:3], colours[0][:3]))

    accents = sorted((c for c in colours[1:] if saturation(c) >= 0.2), key=saturation,
                     reverse=True)
    rest = sorted(colours[1:], key=distance, reverse=True)
    for colour in accents + rest:
        name = colour_name(colour)
        if name != first:
            return "%s & %s" % (first, name)
    return first


def hex_colours(colours):
    return " ".join("#%02X%02X%02X" % tuple(int(round(min(max(c, 0.0), 1.0) * 255))
                                           for c in colour[:3]) for colour in colours)
