"""A line of text made of copies of one part - The Forge's "Forge Text".

The letters are drawn in a panel font (objects/shapes/panel_font.py): each
stroke is laid with the part end to end, every copy scaled so its long side
spans its share of the stroke. It lies flat, the text reading along +X, and
stays one object whose text, font and size can be changed after - everything
it shares with the other forged objects is in objects/shapes/forged.py.
"""

import numpy as np

from ...utils import frames
from . import panel_font
from .forged import Forged, LayoutRefused

# the part it is made of
PART_ID = "STORAGEPANEL"


class Text(Forged):

    FORM = "TEXT"
    LABEL = "Text"

    @classmethod
    def initialise(cls, settings):
        """Nothing to start from the part - the letter height sets the size.
        The text itself is kept by Reset."""

    @classmethod
    def create_text(cls, source, text, font, letter_height, bold=False, italic=False):
        """Turn a part into a line of text, in its place.

        Returns:
            bpy.types.Object: The new object.
        """
        forged_obj = cls.create(source)
        settings = forged_obj.charon_forged
        with Forged.suspended():
            settings.text_body = text
            settings.text_font = font
            settings.text_bold = bold
            settings.text_italic = italic
            settings.letter_height = letter_height
        Forged.update(forged_obj)
        return forged_obj

    @classmethod
    def compute(cls, settings):
        text = settings.text_body.strip()
        if not text:
            raise LayoutRefused("Enter some text")
        # a text saved in a family since taken out reads as no family at all
        family = settings.text_font or panel_font.DEFAULT_FAMILY
        font = panel_font.get_font(family, settings.text_bold, settings.text_italic)
        if font is None:
            raise LayoutRefused("Unknown font")
        missing = font.missing(text)
        if missing:
            raise LayoutRefused("No %s in this font" % " ".join(missing))

        turn, centre = Forged.turn_and_centre(settings)
        # the footprint's longer side is the part's long side, along the
        # frame's x or its y
        width, height = Forged.footprint(settings)
        long_along_x = width >= height
        long_side, short_side = (width, height) if long_along_x else (height, width)
        thin = min(settings.part_size) * settings.tile_scale

        unit = settings.letter_height / font.height
        spacing = settings.letter_spacing / unit
        panels, line_width = panel_font.plan(text, font, long_side / short_side, spacing)
        panels = np.array(panels, dtype=np.float64)
        centre_x, centre_y, angles, lengths = panels.T
        # each copy's size against the part at its own scale
        sizes = lengths * unit / long_side

        # laid face down - the side opposite the part's front faces up, the
        # side a QR code is read from too - its tops flush whatever its size
        top = thin * sizes.max()
        centres = np.stack([
            (centre_x - line_width / 2) * unit,
            (centre_y - font.height / 2) * unit,
            top - thin * sizes / 2,
        ], axis=-1)
        direction = np.stack([np.cos(angles), np.sin(angles), np.zeros_like(angles)], axis=-1)
        across = np.stack([-np.sin(angles), np.cos(angles), np.zeros_like(angles)], axis=-1)
        normals = np.tile((0.0, 0.0, -1.0), (len(panels), 1))
        if long_along_x:
            along, up = direction, -across
        else:
            along, up = across, direction

        positions, rotations = frames.place(centres, normals, along, up, turn, centre,
                                           Forged.copy_scale(settings) * sizes)
        info = "%.1f m long" % (line_width * unit)
        return positions, rotations, {"shape_info": info}, sizes

