import math

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from ..builder import station_colours, station_design, station_library
from ..objects.circle import Circle  # noqa: F401 - registers the kind
from ..objects.cuboid import Cuboid  # noqa: F401 - registers the kind
from ..objects.forged import Forged
from ..objects.polygon import Polygon  # noqa: F401 - registers the kind
from ..objects.rectangle import Rectangle  # noqa: F401 - registers the kind
from ..objects.shape import Shape  # noqa: F401 - registers the kind
from ..objects.sphere import Sphere
from ..utils import circle_topology, polygon_topology, rectangle_topology, shape_topology
from . import the_forge_operators, the_forge_presentation


def _on_changed(self, context):
    if self.form and not Forged.is_suspended():
        Forged.update(self.id_data)


def _on_radius_changed(self, context):
    if Forged.is_suspended():
        return
    self.counts_from_radius = True
    _on_changed(self, context)


def _on_span_changed(self, context):
    """Top, bottom or sweep changed: typed-in counts are scaled with the
    arc they cover, so the copies keep their spacing instead of piling up."""
    if Forged.is_suspended():
        return
    if not self.counts_from_radius:
        Sphere.rescale_counts(self)
    _on_changed(self, context)


def _on_topology_changed(self, context):
    if Forged.is_suspended():
        return
    # counts mean something else in each topology, so start from the radius
    self.counts_from_radius = True
    _on_changed(self, context)


def _on_count_changed(self, context):
    if Forged.is_suspended():
        return
    self.counts_from_radius = False
    Sphere.record_density(self)
    _on_changed(self, context)


def _on_vertices_changed(self, context):
    """Step the corner count to one the style can have."""
    if Forged.is_suspended():
        return
    snapped = shape_topology.snap_vertices(self.shape_style, self.vertices, self.last_vertices)
    with Forged.suspended():
        self.vertices = snapped
        self.last_vertices = snapped
    _on_changed(self, context)


TOPOLOGIES = [
    ("RINGS", "Rings", "Rings of latitude, each holding as many copies as fit around it"),
    ("MERIDIANS", "Meridians",
     "One ring of copies from pole to pole, turned around the axis. "
     "Copies close in on each other towards the poles"),
    ("GEODESIC", "Geodesic",
     "Copies on the points of a subdivided icosahedron, evenly spread with no crowded poles"),
    ("CUBE", "Cube",
     "A grid on each face of a cube, pushed out onto the sphere. Square parts line up in rows"),
    ("SPIRAL", "Spiral", "Copies along a golden spiral, the most even spread"),
]

SHAPE_STYLES = [
    (shape_topology.EVEN, "Even",
     "Corners spread as evenly as they go, edges pulled to one length: 4 is a "
     "tetrahedron, 6 an octahedron, 12 an icosahedron"),
    (shape_topology.PYRAMID, "Pyramid", "A flat base with one corner above it"),
    (shape_topology.BIPYRAMID, "Double Pyramid", "A ring with a corner above it and one below"),
    (shape_topology.PRISM, "Prism", "Two matching rings, one over the other - 8 corners is a cube"),
    (shape_topology.ANTIPRISM, "Antiprism",
     "Two rings, the top one turned half a step, joined by triangles"),
    (shape_topology.TORUS, "Donut", "A ring with a round tube - sweep it short for an arch"),
    (shape_topology.CYLINDER, "Cylinder", "A round column, or an open tube with its ends off"),
    (shape_topology.CONE, "Cone", "A cone to a point, or cut off flat with a top size"),
    (shape_topology.CAPSULE, "Capsule", "A cylinder with a half sphere on each end"),
    (shape_topology.STAR, "Star", "A star-shaped column, any number of points"),
]

CIRCLE_TOPOLOGIES = [
    (circle_topology.RINGS, "Rings",
     "Rings following the outline in to the middle, each part lined up along its ring"),
    (circle_topology.ROWS, "Rows", "Straight rows, each filled from one side of the circle to the other"),
    (circle_topology.GRID, "Grid",
     "One square grid, the columns lined up like tiles - Stagger shifts every other row like bricks"),
    (circle_topology.SPOKES, "Spokes", "Lines of parts running out from the middle"),
    (circle_topology.SPIRAL, "Spiral",
     "Spiral arms winding out from a part in the middle, each part lined up along its arm"),
    (circle_topology.SUNFLOWER, "Sunflower",
     "Parts along a golden spiral from a part in the middle, an even, organic spread"),
]

RECT_TOPOLOGIES = [
    (rectangle_topology.ROWS, "Rows", "Straight rows, each running corner to corner"),
    (rectangle_topology.BRICK, "Brick", "Rows with every other one shifted half a part over"),
    (rectangle_topology.FRAMES, "Frames",
     "Frames following the edges in to the middle, each part lined up along its side"),
    (rectangle_topology.DIAGONAL, "Diagonal", "A grid turned 45°, only whole parts kept"),
]

POLYGON_TOPOLOGIES = [
    (polygon_topology.FRAMES, "Frames",
     "Frames following the sides in to the middle, each part lined up along its side"),
    (polygon_topology.ROWS, "Rows", "Straight rows, as long as fits across, whole parts only"),
    (polygon_topology.WEDGES, "Wedges",
     "A wedge from the middle to each side, filled with rows along that side"),
]

RIM_STYLES = [
    (circle_topology.FLAT, "Flat", "Lying flat along the outline"),
    (circle_topology.WALL, "Wall", "Standing up along the outline, facing out"),
]


# The settings of an object The Forge made, stored on it as
# object.charon_forged - see objects/forged.py. `form` says which kind it is
# (objects/sphere.py, objects/shape.py) and is empty on anything else.
class CharonForged(bpy.types.PropertyGroup):

    form: StringProperty()
    # the object holding the part's mesh, which the modifier places
    part_object: PointerProperty(type=bpy.types.Object)
    object_id: StringProperty()
    base_scale: FloatProperty(default=1.0)
    # measured off the part once - see Forged.measure
    # the part's size along its own axes
    part_size: FloatVectorProperty(size=3)
    pitch_around: FloatProperty(default=1.0)
    pitch_up: FloatProperty(default=1.0)
    base_rotation: FloatVectorProperty(size=3, subtype="EULER")
    centre_offset: FloatVectorProperty(size=3)
    # the scale of the copies on show, which the export reads
    applied_scale: FloatProperty(default=1.0)
    part_count: IntProperty()
    message: StringProperty()

    # Every kind ---
    tile_scale: FloatProperty(
        name="Part Scale", description="Scale every copy",
        default=1.0, min=0.1, max=10.0, update=_on_changed,
    )
    rotation: FloatVectorProperty(
        name="Rotation", description="Rotate every copy on its own local axes",
        size=3, subtype="EULER", update=_on_changed,
    )

    # Spheres ---
    # True while rings and segments follow the radius; typing either one in
    # holds them until the radius changes again
    counts_from_radius: BoolProperty(default=True)
    # how closely typed-in counts are spaced - see Sphere.record_density
    ring_density: FloatProperty()
    around_density: FloatProperty()

    topology: EnumProperty(
        name="Topology", description="How the copies are spread over the sphere",
        items=TOPOLOGIES, default="RINGS", update=_on_topology_changed,
    )
    radius: FloatProperty(
        name="Radius", default=10.0, min=0.1, soft_max=500.0, unit="LENGTH",
        update=_on_radius_changed,
    )
    rings: IntProperty(
        name="Rings", description="Rings of copies from bottom to top",
        default=8, min=1, max=500, update=_on_count_changed,
    )
    segments: IntProperty(
        name="Around", description="Copies around the equator",
        default=12, min=1, max=100000, update=_on_count_changed,
    )
    pole_density: FloatProperty(
        name="Pole Density",
        description="Extra copies in the rings towards the top and bottom, "
                    "on top of what covers them",
        default=0.0, min=0.0, soft_max=2.0, max=5.0, update=_on_changed,
    )
    stagger: BoolProperty(
        name="Stagger", description="Offset every other ring by half a copy",
        default=False, update=_on_changed,
    )
    top: FloatProperty(
        name="Top", description="Highest latitude, 90° for a closed top",
        default=math.pi / 2, min=-math.pi / 2, max=math.pi / 2, subtype="ANGLE",
        update=_on_span_changed,
    )
    bottom: FloatProperty(
        name="Bottom", description="Lowest latitude, 0° for a dome",
        default=-math.pi / 2, min=-math.pi / 2, max=math.pi / 2, subtype="ANGLE",
        update=_on_span_changed,
    )
    sphere_scale: FloatVectorProperty(
        name="Scale", description="Stretch the sphere along X, Y and Z into an ellipsoid",
        size=3, default=(1.0, 1.0, 1.0), min=0.05, soft_max=10.0, update=_on_changed,
    )
    sweep: FloatProperty(
        name="Sweep", description="How far around the sphere goes",
        default=2 * math.pi, min=math.radians(1), max=2 * math.pi, subtype="ANGLE",
        update=_on_span_changed,
    )

    # Shapes ---
    shape_style: EnumProperty(
        name="Style", description="What kind of shape the corners make",
        items=SHAPE_STYLES, default=shape_topology.EVEN, update=_on_vertices_changed,
    )
    vertices: IntProperty(
        name="Vertices", description="How many corners the shape has",
        default=4, min=4, max=shape_topology.MAX_VERTICES, update=_on_vertices_changed,
    )
    last_vertices: IntProperty(default=4)
    size: FloatProperty(
        name="Size", description="How far the farthest corner is from the centre",
        default=5.0, min=0.1, soft_max=500.0, unit="LENGTH", update=_on_changed,
    )
    stretch: FloatVectorProperty(
        name="Stretch", description="Stretch the shape along each axis",
        size=3, default=(1.0, 1.0, 1.0), min=0.05, soft_max=10.0, update=_on_changed,
    )
    fill_faces: BoolProperty(
        name="Faces", description="Fill every face with rows of the part",
        default=True, update=_on_changed,
    )
    fill_edges: BoolProperty(
        name="Edges", description="Line every edge with the part, end to end",
        default=False, update=_on_changed,
    )
    fill_corners: BoolProperty(
        name="Corners", description="Put the part on every corner",
        default=False, update=_on_changed,
    )
    face_margin: FloatProperty(
        name="Face Margin",
        description="Keep the parts filling a face this far in from its edges - "
                    "room for the edge parts. Negative lets them out past the edges",
        default=0.0, soft_min=-10.0, soft_max=10.0, unit="LENGTH", update=_on_changed,
    )
    follow_edges: BoolProperty(
        name="Follow Edges",
        description="Fill faces in rings that follow their outline, every part lined up "
                    "with its nearest edge, instead of straight rows that step along "
                    "slanted edges",
        default=False, update=_on_changed,
    )
    corner_overlap: FloatProperty(
        name="Corner Overlap",
        description="How far Follow Edges rows run on past their own edge's strip into "
                    "the next one, in part heights - the same at every depth, so the "
                    "seams overlap evenly. 0 keeps them apart, leaving gaps along the seams",
        default=0.5, min=0.0, soft_max=2.0, max=10.0, update=_on_changed,
    )
    spacing: FloatProperty(
        name="Spacing",
        description="Gap between neighbouring parts, across rows, between rows "
                    "and along edges. Negative overlaps them",
        default=0.0, soft_min=-2.0, soft_max=10.0, unit="LENGTH", update=_on_changed,
    )
    shape_info: StringProperty()

    # Shapes built face by face ---
    sides: IntProperty(
        name="Sides", description="Steps around the shape - or a star's points",
        default=24, min=3, max=256, update=_on_changed,
    )
    tube_sides: IntProperty(
        name="Tube Sides", description="Steps around the donut's tube",
        default=12, min=3, max=128, update=_on_changed,
    )
    thickness: FloatProperty(
        name="Thickness", description="How thick the donut's tube is, against the ring",
        default=0.35, min=0.02, max=0.98, subtype="FACTOR", update=_on_changed,
    )
    shape_height: FloatProperty(
        name="Height", description="How tall it is, in sizes - 2 is as tall as it is wide",
        default=2.0, min=0.0, soft_max=20.0, update=_on_changed,
    )
    top_size: FloatProperty(
        name="Top Size", description="The top against the base - 0 comes to a point",
        default=0.0, min=0.0, soft_max=2.0, update=_on_changed,
    )
    inner_size: FloatProperty(
        name="Inner Size", description="How far in the notches between a star's points go",
        default=0.5, min=0.02, max=0.98, subtype="FACTOR", update=_on_changed,
    )
    cap_rings: IntProperty(
        name="Cap Rings", description="Rings in each rounded end",
        default=4, min=1, max=64, update=_on_changed,
    )
    capped: BoolProperty(
        name="Cap Ends", description="Close the ends - off leaves an open tube or cut",
        default=True, update=_on_changed,
    )
    shape_sweep: FloatProperty(
        name="Sweep", description="How far round it goes - short of a full turn for an arch or a slice",
        default=2 * math.pi, min=math.radians(1), max=2 * math.pi, subtype="ANGLE",
        update=_on_changed,
    )

    # Cuboids ---
    dimensions: FloatVectorProperty(
        name="Dimensions", description="Width, depth and height",
        size=3, default=(4.0, 4.0, 4.0), min=0.01, soft_max=500.0, subtype="XYZ_LENGTH",
        update=_on_changed,
    )

    # Circles - with radius, shape_sweep, stagger and the fill settings above ---
    circle_topology: EnumProperty(
        name="Fill Pattern", description="How the parts fill the circle's face",
        items=CIRCLE_TOPOLOGIES, default=circle_topology.RINGS, update=_on_changed,
    )
    circle_scale: FloatVectorProperty(
        name="Scale", description="Stretch the circle along X and Y into an ellipse",
        size=2, default=(1.0, 1.0), min=0.05, soft_max=10.0, subtype="XYZ",
        update=_on_changed,
    )
    hole_size: FloatProperty(
        name="Hole", description="Leave the middle empty - 0 fills it, 0.5 leaves a band "
                                 "half the radius wide, the same width all the way round",
        default=0.0, min=0.0, max=0.95, subtype="FACTOR", update=_on_changed,
    )
    spokes: IntProperty(
        name="Spokes", description="Lines of parts running out from the middle",
        default=12, min=1, max=720, update=_on_changed,
    )
    rim_style: EnumProperty(
        name="Circumference", description="How the parts lining the outline sit",
        items=RIM_STYLES, default=circle_topology.FLAT, update=_on_changed,
    )
    rim_offset: FloatProperty(
        name="Offset",
        description="Move the parts lining the outline this far out from the face - "
                    "negative moves them in over it",
        default=0.0, soft_min=-10.0, soft_max=10.0, unit="LENGTH", update=_on_changed,
    )
    centre_density: FloatProperty(
        name="Centre Density",
        description="Pack the parts closer towards the middle, where tight rings and turns "
                    "leave wedge-shaped gaps between them. 1 closes them at the parts' "
                    "outer edges; the outer rings hardly change",
        default=0.0, min=0.0, soft_max=2.0, max=5.0, update=_on_changed,
    )
    spiral_arms: IntProperty(
        name="Arms", description="How many spiral arms wind out from the middle",
        default=1, min=1, max=64, update=_on_changed,
    )

    # Polygons - with radius, circle_scale, hole_size, the rim and the fill settings above ---
    polygon_topology: EnumProperty(
        name="Fill Pattern", description="How the parts fill the polygon's face",
        items=POLYGON_TOPOLOGIES, default=polygon_topology.FRAMES, update=_on_changed,
    )
    polygon_sides: IntProperty(
        name="Sides", description="How many sides the polygon has",
        default=6, min=3, max=64, update=_on_changed,
    )

    # Rectangles and squares - with hole_size, the rim and the fill settings above ---
    rect_topology: EnumProperty(
        name="Fill Pattern", description="How the parts fill the rectangle's face",
        items=RECT_TOPOLOGIES, default=rectangle_topology.ROWS, update=_on_changed,
    )
    rect_size: FloatVectorProperty(
        name="Size", description="Width and height - equal for a square, apart for a rectangle",
        size=2, default=(10.0, 6.0), min=0.01, soft_max=500.0, subtype="XYZ_LENGTH",
        update=_on_changed,
    )


# State for The Forge panel, stored on the scene as scene.charon_the_forge.
# The station switches keep nothing themselves - they read and set whether
# the station's objects are hidden, so they always match the viewport.
class TheForge(bpy.types.PropertyGroup):
    station_selectable: BoolProperty(
        name="Selectable",
        description="Let the station's pieces be clicked on and selected - off keeps "
                    "them out of the way while building inside it",
        get=lambda self: station_library.is_selectable(),
        set=lambda self, value: station_library.set_selectable(value),
    )
    show_station_exterior: BoolProperty(
        name="Exterior", description="Show the station's exterior",
        get=lambda self: station_library.is_part_shown(station_library.EXTERIOR),
        set=lambda self, value: station_library.show_part(station_library.EXTERIOR, value),
    )
    show_station_core: BoolProperty(
        name="Core", description="Show the station's core - its main hall, floor and roof",
        get=lambda self: station_library.is_section_shown("CORE"),
        set=lambda self, value: station_library.show_section("CORE", value),
    )
    show_station_runway: BoolProperty(
        name="Runway", description="Show the station's runway - its hangar, floor and roof",
        get=lambda self: station_library.is_section_shown("RUNWAY"),
        set=lambda self, value: station_library.show_section("RUNWAY", value),
    )
    show_station_core_roof: BoolProperty(
        name="Roof", description="Show the core's roof - off to see into it from above",
        get=lambda self: not station_library.is_roof_hidden("CORE"),
        set=lambda self, value: station_library.hide_roof("CORE", not value),
    )
    show_station_runway_roof: BoolProperty(
        name="Roof", description="Show the runway's roof - off to see into it from above",
        get=lambda self: not station_library.is_roof_hidden("RUNWAY"),
        set=lambda self, value: station_library.hide_roof("RUNWAY", not value),
    )


classes = (
    CharonForged,
    TheForge,
) + the_forge_operators.classes + the_forge_presentation.classes


def register():
    station_colours.register()
    station_design.register()
    for _class in classes:
        bpy.utils.register_class(_class)
    bpy.types.Scene.charon_the_forge = PointerProperty(type=TheForge)
    bpy.types.Object.charon_forged = PointerProperty(type=CharonForged)


def unregister():
    del bpy.types.Object.charon_forged
    del bpy.types.Scene.charon_the_forge
    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)
    station_design.unregister()
    station_colours.unregister()
