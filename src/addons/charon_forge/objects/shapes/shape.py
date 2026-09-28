"""Shapes made of copies of one part.

A shape is a style - a hull from a corner count (Even, Pyramid, Prism...) or
one built face by face (Donut, Cylinder, Cone, Capsule, Star) - sized and
stretched (objects/shapes/shape_topology.py). The part fills its faces in rows or in
rings following their outline, lines its edges, sits on its corners, or any
mix of the three, and never reaches past a face's boundary or an edge's
ends. Everything it shares with the other forged objects is in
objects/shapes/forged.py.
"""

from ...utils import frames
from . import shape_topology as topology
from .forged import Forged


class Shape(Forged):

    FORM = "SHAPE"
    LABEL = "Shape"

    @classmethod
    def initialise(cls, settings):
        # big enough that every face of the starting tetrahedron holds
        # several rows of the part, and a curved style several rings
        settings.size = max(5 * max(settings.pitch_around, settings.pitch_up), 0.1)

    @classmethod
    def build(cls, settings):
        """The mesh of the shape its settings describe."""
        return topology.build(
            settings.shape_style,
            size=settings.size,
            stretch=settings.stretch,
            vertices=settings.vertices,
            sides=settings.sides,
            tube_sides=settings.tube_sides,
            thickness=settings.thickness,
            height=settings.shape_height,
            top=settings.top_size,
            inner=settings.inner_size,
            rings=settings.cap_rings,
            capped=settings.capped,
            sweep=settings.shape_sweep,
        )

    @classmethod
    def compute(cls, settings):
        mesh = cls.build(settings)
        # fitted by the room the part takes unturned; its local rotation
        # only turns each copy in place
        turn, centre = Forged.turn_and_centre(settings)
        width, height = Forged.footprint(settings)
        centres, normals, along, up = topology.fill(
            mesh, width, height,
            # faces only for now - lining the edges and corners is left off
            faces_on=True,
            edges_on=False,
            corners_on=False,
            margin=settings.face_margin,
            spacing=settings.spacing,
            follow_edges=settings.follow_edges,
            overlap=settings.corner_overlap,
        )
        centres, normals, along, up = Forged.as_triangles(settings, centres, normals, along, up)
        positions, rotations = frames.place(
            centres, normals, along, up, turn, centre, Forged.copy_scale(settings)
        )
        info = "%d corners, %d edges, %d faces" % (
            len(mesh.vertices), len(mesh.edges), len(mesh.faces)
        )
        return positions, rotations, {"shape_info": info}
