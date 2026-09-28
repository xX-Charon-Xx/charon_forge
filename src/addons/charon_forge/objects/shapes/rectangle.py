"""Flat squares and rectangles made of copies of one part.

It starts as a square and its width and height can be set apart. It lies
flat, its face filled with the part in rows, bricks, frames or a diagonal
grid, and its edges lined with it, lying flat or standing as walls. It can
have a hole in the middle, leaving a band the same width on every side. The layout
is objects/shapes/rectangle_topology.py; everything it shares with the other forged
objects is in objects/shapes/forged.py.
"""

from ...utils import frames
from . import rectangle_topology as topology
from .forged import Forged, LayoutRefused


class Rectangle(Forged):

    FORM = "RECTANGLE"
    # the Square button makes them; its width and height can then be set apart
    LABEL = "Square"

    @classmethod
    def initialise(cls, settings):
        side = max(7 * max(settings.pitch_around, settings.pitch_up), 0.1)
        settings.rect_size = (side, side)

    @classmethod
    def compute(cls, settings):
        width_x, width_y = settings.rect_size
        plate = topology.Plate(width_x, width_y, margin=settings.face_margin,
                               hole=settings.hole_size)
        turn, centre = Forged.turn_and_centre(settings)
        width, height = Forged.footprint(settings)

        estimate = topology.estimate(plate, width, height, settings.spacing,
                                     True, False)
        if estimate > 2 * Forged.MAX_PARTS:
            raise LayoutRefused("About %d parts, the most is %d" % (estimate, Forged.MAX_PARTS))

        centres, normals, along, up, detail = topology.fill(
            plate, settings.rect_topology, width, height,
            spacing=settings.spacing,
            faces_on=True,
            rim_on=False,
            rim_style=settings.rim_style,
            rim_offset=settings.rim_offset,
        )
        centres, normals, along, up = Forged.as_triangles(settings, centres, normals, along, up)
        positions, rotations = frames.place(
            centres, normals, along, up, turn, centre, Forged.copy_scale(settings)
        )
        info = "%.2f x %.2f" % (width_x, width_y)
        if detail:
            info += ", " + detail
        return positions, rotations, {"shape_info": info}
