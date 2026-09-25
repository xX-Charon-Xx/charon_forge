"""Cuboids made of copies of one part - a box of any width, depth and height.

Unlike the other shapes (objects/shape.py) a cuboid's faces are rectangles,
so each is filled as a grid corner to corner: every row and column starts at
one edge of the face and ends at the other, the parts at least Spacing
apart. Face Margin moves the faces out from the box instead of in from their
edges.
"""

import numpy as np

from ..utils import frames
from ..utils import shape_topology as topology
from .forged import Forged
from .shape import Shape


class Cuboid(Shape):

    FORM = "CUBOID"
    LABEL = "Cuboid"

    @classmethod
    def initialise(cls, settings):
        # seven parts to a side to begin with
        side = max(7 * max(settings.pitch_around, settings.pitch_up), 0.1)
        settings.dimensions = (side, side, side)
        settings.size = 1.0

    @classmethod
    def build(cls, settings):
        dimensions = np.asarray(settings.dimensions, dtype=np.float64) * settings.size
        return topology.build(topology.CUBOID, stretch=dimensions)

    @classmethod
    def compute(cls, settings):
        mesh = cls.build(settings)
        turn, centre = Forged.turn_and_centre(settings)
        width, height = Forged.footprint(settings)
        face_frames = topology.face_frames(mesh)

        # faces only for now - lining the edges and corners is left off
        centres, normals, along, up = topology.fill_rectangles(
            mesh, face_frames, width, height,
            spacing=settings.spacing, offset=settings.face_margin,
        )

        positions, rotations = frames.place(
            centres, normals, along, up, turn, centre, Forged.copy_scale(settings)
        )
        dimensions = np.asarray(settings.dimensions) * settings.size
        info = "%.2f x %.2f x %.2f" % tuple(dimensions)
        return positions, rotations, {"shape_info": info}
