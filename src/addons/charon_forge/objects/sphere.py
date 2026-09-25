"""Spheres made of copies of one part, kept as a single object.

How the copies are spread over the sphere is its topology - rings of
latitude, meridians, a geodesic, a cube grid or a spiral; see
utils/sphere_topology.py. Every copy's position and rotation comes out of one
vectorised numpy pass (about a millisecond for thousands of copies), and is
written to the sphere's own mesh as a point with a rotation attribute. A
geometry nodes modifier puts the part on every point as an instance of one
mesh, drawn from a single GPU batch - nothing is copied or made real, which
keeps dragging a slider smooth on big spheres.

The part's mesh sits on a holder object in no scene, which the modifier
reads. The copies are instances of geometry, not of an object, so Blender
draws them as the sphere and its colour properties paint them.

A sphere is also a group (objects/group.py): it exports as its parts, takes
the group colour tools, and Ungroup - Split in The Forge - turns it back into
normal parts. Its child cache is written when something reads it - see
refresh_child_cache.

Its settings live on the object, as object.charon_sphere (addon/the_forge.py).
"""

import contextlib
import json
import math
import time
import uuid

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

from .. import materials
from ..materials.properties import MESH_TAG
from ..utils import sphere_topology as topology
from ..utils.mesh_utils import mesh_bounds
from .group import Group
from .part import Part


class Sphere:

    # a layout needing more copies than this is refused rather than built
    MAX_PARTS = 3000
    MIN_PITCH = 0.01

    NODE_GROUP = "Charon Forge Sphere"
    NODE_GROUP_VERSION = 3
    MODIFIER = "Charon Forge Sphere"
    ROTATION_ATTRIBUTE = "charon_rotation"

    # the surface frame the part is laid into - x along, y up, z out - as
    # seen at latitude and longitude 0, where those are the world's Y, Z and X
    SURFACE_FRAME = Matrix(((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))

    # the topologies whose counts are rings and copies around, and so are
    # rescaled when the arc they cover changes
    ARC_TOPOLOGIES = (topology.RINGS, topology.MERIDIANS)

    _suspended = 0

    # Updates ---
    @staticmethod
    @contextlib.contextmanager
    def suspended():
        """Settings changed inside this don't update the sphere."""
        Sphere._suspended += 1
        try:
            yield
        finally:
            Sphere._suspended -= 1

    @staticmethod
    def is_suspended():
        return Sphere._suspended > 0

    @staticmethod
    def is_sphere(bpy_object):
        return (
            bpy_object is not None
            and bpy_object.type == "MESH"
            and bpy_object.charon_sphere.is_sphere
            and Group.PROP_GROUP_ID in bpy_object
        )

    # Measuring the part ---
    @staticmethod
    def part_to_surface(size):
        """The rotation from the part's own axes into the surface frame, the
        thinnest side facing out - a floor or panel lies flat on the sphere."""
        face = min(range(3), key=lambda i: size[i])
        around, up = (face + 1) % 3, (face + 2) % 3
        columns = [None, None, None]
        columns[around] = Vector((1.0, 0.0, 0.0))
        columns[up] = Vector((0.0, 1.0, 0.0))
        columns[face] = Vector((0.0, 0.0, 1.0))
        return Matrix(columns).transposed()

    @staticmethod
    def measure(settings, mesh):
        """Store what the layout needs to know about the part."""
        size, centre = mesh_bounds(mesh)
        size = size * settings.base_scale
        orientation = Sphere.part_to_surface(size)
        extent = Vector([
            sum(abs(orientation[row][column]) * size[column] for column in range(3))
            for row in range(3)
        ])
        settings.pitch_around = max(extent.x, Sphere.MIN_PITCH)
        settings.pitch_up = max(extent.y, Sphere.MIN_PITCH)
        settings.base_rotation = (Sphere.SURFACE_FRAME @ orientation).to_euler("XYZ")
        settings.centre_offset = Sphere.SURFACE_FRAME @ orientation @ centre

    # Counts ---
    @staticmethod
    def _latitudes(settings):
        return tuple(sorted((settings.bottom, settings.top)))

    @staticmethod
    def _span(settings):
        bottom, top = Sphere._latitudes(settings)
        return top - bottom

    @staticmethod
    def counts(settings):
        """(rings, segments) - the two counts, in whatever the topology uses
        them for - worked out from the radius, or as typed in."""
        if not settings.counts_from_radius:
            return settings.rings, settings.segments

        radius, kind = settings.radius, settings.topology
        pitch_around, pitch_up = settings.pitch_around, settings.pitch_up
        rings, segments = settings.rings, settings.segments

        if kind in Sphere.ARC_TOPOLOGIES:
            steps = round(radius * Sphere._span(settings) / pitch_up)
            rings = steps + 1 if steps > 0 else 1
            segments = max(1, round(radius * settings.sweep / pitch_around))
        elif kind == topology.GEODESIC:
            # neighbouring points one part apart
            pitch = (pitch_around + pitch_up) / 2
            rings = max(1, round(topology.ICOSAHEDRON_EDGE * radius / pitch))
        elif kind == topology.CUBE:
            # each face spans a quarter turn of the sphere
            rings = max(1, round(math.pi / 2 * radius / pitch_around))
        elif kind == topology.SPIRAL:
            # as many as the whole sphere's area holds
            segments = max(1, round(4 * math.pi * radius * radius / (pitch_around * pitch_up)))
        return rings, segments

    @staticmethod
    def _whole_sphere_count(kind, rings, segments):
        """Roughly how many points a topology makes before anything outside
        top, bottom and sweep is dropped."""
        if kind == topology.GEODESIC:
            return 10 * rings * rings + 2
        if kind == topology.CUBE:
            return 6 * rings * rings
        if kind == topology.SPIRAL:
            return segments
        return rings * segments

    @staticmethod
    def record_density(settings):
        """Remember how closely typed-in counts are spaced - rings per radian
        of latitude, copies per radian around - for rescale_counts."""
        span = Sphere._span(settings)
        settings.ring_density = (settings.rings - 1) / span if span > 1e-6 else 0.0
        settings.around_density = settings.segments / settings.sweep

    @staticmethod
    def rescale_counts(settings):
        """Work typed-in counts out again for the arc they now cover, at the
        spacing they were typed in at, so shrinking the arc drops copies
        rather than squeezing them together. Always from the recorded
        spacing, never from the last counts, so dragging a slider doesn't
        drift or stick.

        Only rings and meridians: the other topologies spread their points
        over the whole sphere and just drop those out of range, so their
        spacing already holds."""
        if settings.topology not in Sphere.ARC_TOPOLOGIES:
            return
        with Sphere.suspended():
            if settings.ring_density > 0.0:
                settings.rings = max(1, round(settings.ring_density * Sphere._span(settings)) + 1)
            if settings.around_density > 0.0:
                settings.segments = max(1, round(settings.around_density * settings.sweep))

    # Layout ---
    @staticmethod
    def _turn_and_centre(settings):
        """The part's rotation into the surface frame with its local rotation,
        and its centre in that frame."""
        base = Euler(settings.base_rotation, "XYZ").to_matrix()
        local = Euler(settings.rotation, "XYZ").to_matrix()
        frame_inverse = Sphere.SURFACE_FRAME.transposed()
        turn = frame_inverse @ base @ local
        centre = frame_inverse @ Vector(settings.centre_offset)
        return np.array(turn, dtype=np.float64), np.array(centre, dtype=np.float64)

    @staticmethod
    def layout(settings, rings, segments):
        """(positions, rotations) of every copy, relative to the sphere."""
        bottom, top = Sphere._latitudes(settings)
        sweep, kind = settings.sweep, settings.topology
        if kind == topology.MERIDIANS:
            frames = topology.meridians(bottom, top, sweep, rings, segments)
        elif kind == topology.GEODESIC:
            frames = topology.geodesic(bottom, top, sweep, rings)
        elif kind == topology.CUBE:
            frames = topology.cube(bottom, top, sweep, rings)
        elif kind == topology.SPIRAL:
            frames = topology.spiral(bottom, top, sweep, segments)
        else:
            frames = topology.rings(
                bottom, top, sweep, rings, segments, settings.pole_density, settings.stagger
            )
        turn, centre = Sphere._turn_and_centre(settings)
        scale = settings.base_scale * settings.tile_scale
        return topology.place(*frames, settings.radius, turn, centre, scale)

    # Node tree ---
    @staticmethod
    def _node_group():
        """Every sphere's modifier: the part on each point, turned by the
        point's rotation and scaled by the Scale input."""
        tree = bpy.data.node_groups.get(Sphere.NODE_GROUP)
        if tree is not None and tree.get("charon_version") == Sphere.NODE_GROUP_VERSION:
            return tree
        if tree is None:
            tree = bpy.data.node_groups.new(Sphere.NODE_GROUP, "GeometryNodeTree")
        else:
            tree.nodes.clear()
            tree.interface.clear()

        interface = tree.interface
        interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        interface.new_socket("Part", in_out="INPUT", socket_type="NodeSocketObject")
        interface.new_socket("Scale", in_out="INPUT", socket_type="NodeSocketFloat")
        interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

        nodes, links = tree.nodes, tree.links
        group_input = nodes.new("NodeGroupInput")
        part = nodes.new("GeometryNodeObjectInfo")
        part.transform_space = "ORIGINAL"
        rotation = nodes.new("GeometryNodeInputNamedAttribute")
        rotation.data_type = "QUATERNION"
        rotation.inputs["Name"].default_value = Sphere.ROTATION_ATTRIBUTE
        instances = nodes.new("GeometryNodeInstanceOnPoints")
        group_output = nodes.new("NodeGroupOutput")

        rotation_output = next(
            (socket for socket in rotation.outputs
             if socket.name == "Attribute" and socket.enabled),
            rotation.outputs[0],
        )
        links.new(group_input.outputs["Part"], part.inputs["Object"])
        links.new(group_input.outputs["Geometry"], instances.inputs["Points"])
        links.new(part.outputs["Geometry"], instances.inputs["Instance"])
        links.new(rotation_output, instances.inputs["Rotation"])
        links.new(group_input.outputs["Scale"], instances.inputs["Scale"])
        links.new(instances.outputs["Instances"], group_output.inputs["Geometry"])

        group_input.location = (0, 0)
        part.location = (220, -60)
        rotation.location = (220, -260)
        instances.location = (440, 0)
        group_output.location = (660, 0)

        tree["charon_version"] = Sphere.NODE_GROUP_VERSION
        return tree

    @staticmethod
    def _set_modifier_inputs(sphere_obj, values):
        tree = Sphere._node_group()
        modifier = sphere_obj.modifiers.get(Sphere.MODIFIER)
        if modifier is None:
            modifier = sphere_obj.modifiers.new(Sphere.MODIFIER, "NODES")
        if modifier.node_group is not tree:
            modifier.node_group = tree
        identifiers = {
            item.name: item.identifier
            for item in tree.interface.items_tree
            if getattr(item, "in_out", None) == "INPUT"
        }
        changed = False
        for name, value in values.items():
            identifier = identifiers.get(name)
            if identifier is not None and modifier.get(identifier) != value:
                modifier[identifier] = value
                changed = True
        return changed

    @staticmethod
    def _write_points(mesh, positions, rotations):
        mesh.clear_geometry()
        mesh.vertices.add(len(positions))
        mesh.vertices.foreach_set("co", positions.astype(np.float32).ravel())
        attribute = mesh.attributes.get(Sphere.ROTATION_ATTRIBUTE)
        if attribute is None:
            attribute = mesh.attributes.new(Sphere.ROTATION_ATTRIBUTE, "QUATERNION", "POINT")
        attribute.data.foreach_set(
            "value", topology.to_quaternions(rotations).astype(np.float32).ravel()
        )
        mesh.update()

    # Spheres ---
    @staticmethod
    def create(source):
        """Turn a part into a sphere of copies of it, in its place.

        Returns:
            bpy.types.Object: The sphere.
        """
        part_mesh = source.data
        object_id = source[Part.PROP_OBJECT_ID].replace("^", "")
        user_data = source.get(Part.PROP_USER_DATA, Part.DEFAULT_USER_DATA)

        # in no scene: only the modifier reads it
        holder = bpy.data.objects.new("%s Sphere Part" % object_id, part_mesh)

        # the colour tools read the part id off the mesh, the way they do a
        # group's
        points = bpy.data.meshes.new("%s Sphere" % object_id)
        points[MESH_TAG] = object_id
        sphere_obj = bpy.data.objects.new("%s Sphere" % object_id, points)
        for collection in source.users_collection:
            collection.objects.link(sphere_obj)
        if not sphere_obj.users_collection:
            bpy.context.scene.collection.objects.link(sphere_obj)
        sphere_obj.matrix_world = Matrix.Translation(source.matrix_world.translation)

        # the colour the part had
        for key in source.keys():
            if key.startswith("nms_"):
                sphere_obj[key] = source[key]
        sphere_obj.color = source.color
        sphere_obj[Part.PROP_USER_DATA] = str(user_data)

        sphere_obj[Group.PROP_GROUP_ID] = str(uuid.uuid4())
        sphere_obj[Group.PROP_IS_MIRROR] = False
        sphere_obj[Group.PROP_ORIGIN_OFFSET] = (0.0, 0.0, 0.0)
        sphere_obj[Group.PROP_CHILD_CACHE] = "{}"

        settings = sphere_obj.charon_sphere
        scale = source.matrix_world.to_scale()
        with Sphere.suspended():
            settings.is_sphere = True
            settings.part_object = holder
            settings.object_id = object_id
            settings.base_scale = (abs(scale.x) + abs(scale.y) + abs(scale.z)) / 3 or 1.0
            Sphere.measure(settings, part_mesh)
            # a dozen copies around the equator to begin with
            settings.radius = max(12 * settings.pitch_around / topology.FULL_TURN, 0.1)
            settings.counts_from_radius = True

        bpy.data.objects.remove(source, do_unlink=True)
        Sphere.update(sphere_obj)
        return sphere_obj

    @staticmethod
    def update(sphere_obj):
        """Lay the sphere out again from its settings."""
        settings = sphere_obj.charon_sphere
        holder = settings.part_object
        if holder is None or holder.data is None:
            settings.message = "The part is gone"
            return

        # refused layouts leave the sphere, and the counts its export reads,
        # as they were
        rings, segments = Sphere.counts(settings)
        if Sphere._whole_sphere_count(settings.topology, rings, segments) > 20 * Sphere.MAX_PARTS:
            settings.message = "Too many parts, the most is %d" % Sphere.MAX_PARTS
            return
        positions, rotations = Sphere.layout(settings, rings, segments)
        if len(positions) > Sphere.MAX_PARTS:
            settings.message = "%d parts, the most is %d" % (len(positions), Sphere.MAX_PARTS)
            return
        settings.message = ""
        settings.part_count = len(positions)
        if settings.counts_from_radius:
            with Sphere.suspended():
                settings.rings = rings
                settings.segments = segments

        Sphere._write_points(sphere_obj.data, positions, rotations)
        if Sphere._set_modifier_inputs(sphere_obj, {
            "Part": holder,
            "Scale": settings.base_scale * settings.tile_scale,
        }):
            # inputs written from Python don't tag the object themselves
            sphere_obj.update_tag()

    @staticmethod
    def local_matrices(sphere_obj):
        """Every copy's matrix relative to the sphere, from its settings - the
        same layout its points were made from."""
        settings = sphere_obj.charon_sphere
        positions, rotations = Sphere.layout(settings, settings.rings, settings.segments)
        scale = settings.base_scale * settings.tile_scale

        matrices = np.zeros((len(positions), 4, 4))
        matrices[:, :3, :3] = rotations * scale
        matrices[:, :3, 3] = positions
        matrices[:, 3, 3] = 1.0
        return matrices

    @staticmethod
    def get_all_spheres():
        """Every sphere in the view layer."""
        spheres = []
        for obj in bpy.context.view_layer.objects:
            try:
                if Sphere.is_sphere(obj):
                    spheres.append(obj)
            except ReferenceError:
                continue
        return spheres

    @staticmethod
    def serialise(sphere_obj):
        """The sphere as the parts it stands for, in the form NMS saves them.

        Args:
            sphere_obj: The sphere to serialise.

        Returns:
            List of serialised part dictionaries.
        """
        settings = sphere_obj.charon_sphere
        object_id = f"^{settings.object_id}"
        user_data = int(sphere_obj.get(Part.PROP_USER_DATA, Part.DEFAULT_USER_DATA))
        time_stamp = int(time.time())
        world = np.array(sphere_obj.matrix_world, dtype=np.float64)

        serialised_objects = []
        for matrix in world @ Sphere.local_matrices(sphere_obj):
            pos, up, at = Group.extract_pos_up_at(Matrix(matrix.tolist()))
            serialised_objects.append({
                Part.PROP_TIMESTAMP: time_stamp,
                Part.PROP_OBJECT_ID: object_id,
                Part.PROP_USER_DATA: user_data,
                Part.PROP_POSITION: [pos[0], pos[1], pos[2]],
                Part.PROP_UP: [up[0], up[1], up[2]],
                Part.PROP_AT: [at[0], at[1], at[2]],
            })
        return serialised_objects

    @staticmethod
    def refresh_child_cache(sphere_obj):
        """Write the sphere's child cache from its settings - what the group
        code reads when it splits it or looks up its colour."""
        settings = sphere_obj.charon_sphere
        matrices = Sphere.local_matrices(sphere_obj)

        user_data = sphere_obj.get(Part.PROP_USER_DATA, Part.DEFAULT_USER_DATA)
        stamp = int(time.time())
        cache = {
            "%s.%04d" % (settings.object_id, index): {
                Group.PROP_OBJECT_ID: settings.object_id,
                Group.PROP_USER_DATA: user_data,
                Group.PROP_TIMESTAMP: stamp,
                Group.PROP_MATRIX_LOCAL: matrix,
            }
            for index, matrix in enumerate(matrices.tolist())
        }
        sphere_obj[Group.PROP_CHILD_CACHE] = json.dumps(cache)
        sphere_obj[Group.PROP_PART_COUNT] = len(matrices)
        sphere_obj[Group.PROP_ORIGIN_MATRIX] = json.dumps(
            [list(row) for row in sphere_obj.matrix_world]
        )

    @staticmethod
    def split(sphere_obj, builder):
        """Turn a sphere into its parts. Returns them."""
        holder = sphere_obj.charon_sphere.part_object
        Sphere.refresh_child_cache(sphere_obj)
        with Sphere.suspended():
            sphere_obj.charon_sphere.is_sphere = False
        # one texture and node group tidy for the lot, not one per part
        with materials.defer_shared_data():
            parts = Group.ungroup_objects(builder, sphere_obj) or []
        if holder is not None and holder.users == 0:
            bpy.data.objects.remove(holder)
        return parts
