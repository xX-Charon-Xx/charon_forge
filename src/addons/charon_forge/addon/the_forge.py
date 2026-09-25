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

from ..objects.sphere import Sphere
from . import the_forge_operators, the_forge_presentation


def _on_sphere_changed(self, context):
    if self.is_sphere and not Sphere.is_suspended():
        Sphere.update(self.id_data)


def _on_radius_changed(self, context):
    if Sphere.is_suspended():
        return
    self.counts_from_radius = True
    _on_sphere_changed(self, context)


def _on_span_changed(self, context):
    """Top, bottom or sweep changed: typed-in counts are scaled with the
    arc they cover, so the copies keep their spacing instead of piling up."""
    if Sphere.is_suspended():
        return
    if not self.counts_from_radius:
        Sphere.rescale_counts(self)
    _on_sphere_changed(self, context)


def _on_topology_changed(self, context):
    if Sphere.is_suspended():
        return
    # counts mean something else in each topology, so start from the radius
    self.counts_from_radius = True
    _on_sphere_changed(self, context)


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


def _on_count_changed(self, context):
    if Sphere.is_suspended():
        return
    self.counts_from_radius = False
    Sphere.record_density(self)
    _on_sphere_changed(self, context)


# A sphere's settings, stored on its object as object.charon_sphere - see
# objects/sphere.py.
class CharonSphere(bpy.types.PropertyGroup):

    is_sphere: BoolProperty()
    # the object holding the part's mesh, which the sphere's modifier places
    part_object: PointerProperty(type=bpy.types.Object)
    object_id: StringProperty()
    base_scale: FloatProperty(default=1.0)
    # measured off the part once - see Sphere.measure
    pitch_around: FloatProperty(default=1.0)
    pitch_up: FloatProperty(default=1.0)
    base_rotation: FloatVectorProperty(size=3, subtype="EULER")
    centre_offset: FloatVectorProperty(size=3)
    part_count: IntProperty()
    message: StringProperty()
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
    tile_scale: FloatProperty(
        name="Part Scale", description="Scale every copy, to close gaps",
        default=1.0, min=0.1, max=10.0, update=_on_sphere_changed,
    )
    rotation: FloatVectorProperty(
        name="Rotation", description="Rotate every copy on its own local axes",
        size=3, subtype="EULER", update=_on_sphere_changed,
    )
    pole_density: FloatProperty(
        name="Pole Density",
        description="Extra copies in the rings towards the top and bottom, "
                    "on top of what covers them",
        default=0.0, min=0.0, soft_max=2.0, max=5.0, update=_on_sphere_changed,
    )
    stagger: BoolProperty(
        name="Stagger", description="Offset every other ring by half a copy",
        default=False, update=_on_sphere_changed,
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
    sweep: FloatProperty(
        name="Sweep", description="How far around the sphere goes",
        default=2 * math.pi, min=math.radians(1), max=2 * math.pi, subtype="ANGLE",
        update=_on_span_changed,
    )


# State for The Forge panel, stored on the scene as scene.charon_the_forge.
class TheForge(bpy.types.PropertyGroup):
    pass


classes = (
    CharonSphere,
    TheForge,
) + the_forge_operators.classes + the_forge_presentation.classes


def register():
    for _class in classes:
        bpy.utils.register_class(_class)
    bpy.types.Scene.charon_the_forge = PointerProperty(type=TheForge)
    bpy.types.Object.charon_sphere = PointerProperty(type=CharonSphere)


def unregister():
    del bpy.types.Object.charon_sphere
    del bpy.types.Scene.charon_the_forge
    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)
