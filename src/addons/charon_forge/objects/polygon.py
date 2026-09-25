"""Flat polygons made of copies of one part.

A regular polygon of any number of sides - stretched along X and Y if need
be - lies flat, its face filled with the part in frames, rows or wedges, and
its edges lined with it, lying flat or standing as walls. It can have a hole
in the middle, leaving a band the same width along every side. The layout
is utils/polygon_topology.py; everything it shares with the other forged
objects is in objects/forged.py.
"""

from ..utils import frames
from ..utils import polygon_topology as topology
from .forged import Forged, LayoutRefused


class Polygon(Forged):

    FORM = "POLYGON"
    LABEL = "Polygon"

    @classmethod
    def initialise(cls, settings):
        # several frames of the part to begin with
        settings.radius = max(6 * max(settings.pitch_around, settings.pitch_up), 0.1)

    @classmethod
    def compute(cls, settings):
        hull = topology.Hull.regular(settings.polygon_sides, settings.radius,
                                     settings.circle_scale)
        plate = topology.Plate(hull, margin=settings.face_margin, hole=settings.hole_size)
        turn, centre = Forged.turn_and_centre(settings)
        width, height = Forged.footprint(settings)

        estimate = topology.estimate(plate, width, height, settings.spacing,
                                     True, False)
        if estimate > 2 * Forged.MAX_PARTS:
            raise LayoutRefused("About %d parts, the most is %d" % (estimate, Forged.MAX_PARTS))

        centres, normals, along, up, detail = topology.fill(
            plate, settings.polygon_topology, width, height,
            spacing=settings.spacing,
            faces_on=True,
            rim_on=False,
            rim_style=settings.rim_style,
            rim_offset=settings.rim_offset,
        )
        positions, rotations = frames.place(
            centres, normals, along, up, turn, centre, Forged.copy_scale(settings)
        )
        corners = hull.vertices
        info = "%d sides, %.2f x %.2f" % (
            len(corners), *(corners.max(axis=0) - corners.min(axis=0))
        )
        if detail:
            info += ", " + detail
        return positions, rotations, {"shape_info": info}
