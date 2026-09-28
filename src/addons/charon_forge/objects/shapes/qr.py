"""A QR code made of copies of one part - The Forge's "Forge a QR Code".

Which panels cover the code's dark squares is worked out in utils/qr_forge.py.
It lies flat, read from above, and stays one object whose content and square
size can be changed after, like a forged text - everything it shares with the
other forged objects is in objects/shapes/forged.py.
"""

import numpy as np

from ...utils import frames, qr_code, qr_forge
from .forged import Forged, LayoutRefused

# the part it is made of
PART_ID = qr_forge.PART_ID

# A forged code never gets scratched or smudged, so it takes the least error
# correction a QR code can have - which is also the smallest code, and the
# fewest panels. (There is no level with none at all.)
ERROR_CORRECTION = "L"

# (text, ratio) -> (squares along a side, panels): planning a big code takes
# a moment, and every other setting lays the same panels out again
_plans = {}


def plan(text, ratio):
    """The code for `text` and the panels covering it, as qr_forge.plan
    gives them.

    Raises:
        qr_code.QRCodeError: When the text doesn't fit a QR code.
    """
    key = (text, round(ratio, 4))
    if key not in _plans:
        if len(_plans) > 32:
            _plans.clear()
        modules = qr_code.encode(text, ERROR_CORRECTION)
        _plans[key] = (len(modules), qr_forge.plan(modules, ratio))
    return _plans[key]


class QRCode(Forged):

    FORM = "QR_CODE"
    LABEL = "QR Code"

    @classmethod
    def initialise(cls, settings):
        """Nothing to start from the part - the square size sets the size.
        The content itself is kept by Reset."""

    @classmethod
    def create_qr_code(cls, source, text, square_size):
        """Turn a part into a QR code, in its place.

        Returns:
            bpy.types.Object: The new object.
        """
        forged_obj = cls.create(source)
        settings = forged_obj.charon_forged
        with Forged.suspended():
            settings.qr_text = text
            settings.qr_square_size = square_size
        Forged.update(forged_obj)
        return forged_obj

    @classmethod
    def compute(cls, settings):
        text = settings.qr_text.strip()
        if not text:
            raise LayoutRefused("Enter some text")

        turn, centre = Forged.turn_and_centre(settings)
        # the footprint's longer side is the part's long side, along the
        # frame's x or its y
        width, height = Forged.footprint(settings)
        long_along_x = width >= height
        long_side, short_side = (width, height) if long_along_x else (height, width)
        thin = min(settings.part_size) * settings.tile_scale

        try:
            squares, panels = plan(text, long_side / short_side)
        except qr_code.QRCodeError as error:
            raise LayoutRefused(str(error).capitalize()) from None

        panels = np.array(panels, dtype=np.float64)
        centre_x, centre_y, panel_along_x, short = panels.T
        unit = settings.qr_square_size
        # each copy's size against the part at its own scale
        sizes = short * unit / short_side

        # laid face down like a forged text - the side opposite the part's
        # front faces up - its tops flush whatever its size. The plan's y
        # runs down the code, the object's up it.
        top = thin * sizes.max()
        centres = np.stack([
            (centre_x - squares / 2) * unit,
            (squares / 2 - centre_y) * unit,
            top - thin * sizes / 2,
        ], axis=-1)
        angles = np.where(panel_along_x > 0.5, 0.0, np.pi / 2)
        direction = np.stack([np.cos(angles), np.sin(angles), np.zeros_like(angles)], axis=-1)
        across = np.stack([-np.sin(angles), np.cos(angles), np.zeros_like(angles)], axis=-1)
        normals = np.tile((0.0, 0.0, -1.0), (len(panels), 1))
        if long_along_x:
            along, up = direction, -across
        else:
            along, up = across, direction

        positions, rotations = frames.place(centres, normals, along, up, turn, centre,
                                           Forged.copy_scale(settings) * sizes)
        info = "%d x %d squares, %.1f m across" % (squares, squares, squares * unit)
        return positions, rotations, {"shape_info": info}, sizes
