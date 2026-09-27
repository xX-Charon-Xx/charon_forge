"""Flat circles made of copies of one part.

A circle - an ellipse once scaled - lies flat, its face filled with the part
in rings, rows, a grid, spokes, spiral arms or a sunflower spread, or its outline lined with it,
lying flat or standing as a wall. It can have a hole in the middle and be
cut short to an arc, from a start angle round to an end angle. The layout is utils/circle_topology.py; everything it
shares with the other forged objects is in objects/forged.py.
"""

from ..utils import circle_topology as topology
from ..utils import frames
from .forged import Forged, LayoutRefused


class Circle(Forged):

    FORM = "CIRCLE"
    LABEL = "Circle"

    @classmethod
    def initialise(cls, settings):
        # several rings of the part to begin with
        settings.radius = max(6 * max(settings.pitch_around, settings.pitch_up), 0.1)

    @classmethod
    def disc(cls, settings):
        start, sweep = frames.arc(settings.sweep_start, settings.sweep_end)
        return topology.Disc(
            settings.radius * settings.circle_scale[0],
            settings.radius * settings.circle_scale[1],
            margin=settings.face_margin,
            hole=settings.hole_size,
            start=start,
            sweep=sweep,
        )

    @classmethod
    def compute(cls, settings):
        disc = cls.disc(settings)
        faces_on = settings.circle_fill == topology.FACE
        turn, centre = Forged.turn_and_centre(settings)
        width, height = Forged.footprint(settings)

        estimate = topology.estimate(
            disc, settings.circle_topology, width, height, settings.spacing,
            faces_on, not faces_on, settings.spokes, settings.centre_density,
        )
        if estimate > 2 * Forged.MAX_PARTS:
            raise LayoutRefused("About %d parts, the most is %d" % (estimate, Forged.MAX_PARTS))

        centres, normals, along, up, detail = topology.fill(
            disc, settings.circle_topology, width, height,
            spacing=settings.spacing,
            faces_on=faces_on,
            rim_on=not faces_on,
            rim_style=settings.rim_style,
            spoke_count=settings.spokes,
            stagger=settings.stagger,
            arms=settings.spiral_arms,
            density=settings.centre_density,
        )
        positions, rotations = frames.place(
            centres, normals, along, up, turn, centre, Forged.copy_scale(settings)
        )
        info = "%.2f x %.2f" % (2 * disc.a, 2 * disc.b)
        if detail and faces_on:
            info += ", " + detail
        return positions, rotations, {"shape_info": info}
