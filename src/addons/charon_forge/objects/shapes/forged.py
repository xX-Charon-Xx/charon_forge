"""Objects The Forge makes out of copies of one part - spheres, shapes.

Each is a single object until it is split. Its kind (objects/shapes/sphere.py,
objects/shapes/shape.py) works out where every copy goes from the object's settings
(object.charon_forged, addon/the_forge.py), in one vectorised numpy pass.
The copies are written to the object's own mesh as points carrying a
rotation, and a geometry nodes modifier puts the part on every point as an
instance of one mesh, drawn from a single GPU batch - nothing is copied or
made real, which keeps dragging a slider smooth however many copies there
are.

The part's mesh sits on a holder object in no scene, which the modifier
reads. The copies are instances of geometry, not of an object, so Blender
draws them as the forged object and its colour properties paint them.

A forged object is also a group (objects/group.py), so the group colour tools
work on it and Ungroup - Split in The Forge - turns it back into normal
parts. It exports through serialise(), which the builder calls.
"""

import contextlib
import json
import time
import uuid

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

from ... import materials
from ...materials.properties import MESH_TAG
from ...utils import frames
from ...utils.mesh_utils import mesh_bounds
from ..group import Group
from ..part import Part
from . import triangles


class LayoutRefused(Exception):
    """A layout that can't be built; its message is shown in the panel."""


class Forged:

    # set by each kind - the settings' `form`, and what its objects are called
    FORM = ""
    LABEL = ""

    # a layout needing more copies than this is refused rather than built
    MAX_PARTS = 10000
    MIN_PITCH = 0.01

    NODE_GROUP = "Charon Forge Sphere"
    NODE_GROUP_VERSION = 5
    MODIFIER = "Charon Forge Sphere"
    PART_NODE = "Part"
    COPIES_NODE = "Copies"
    ROTATION_ATTRIBUTE = "charon_rotation"
    # each copy's scale, the object's own times its size against the rest
    SCALE_ATTRIBUTE = "charon_scale"

    # the surface frame a part is laid into - x along, y up, z out - as seen
    # where a sphere's latitude and longitude are 0: the world's Y, Z and X
    SURFACE_FRAME = Matrix(((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))

    _kinds = {}
    _suspended = 0

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.FORM:
            Forged._kinds[cls.FORM] = cls

    # Updates ---
    @staticmethod
    @contextlib.contextmanager
    def suspended():
        """Settings changed inside this don't update the object."""
        Forged._suspended += 1
        try:
            yield
        finally:
            Forged._suspended -= 1

    @staticmethod
    def is_suspended():
        return Forged._suspended > 0

    @staticmethod
    def is_forged(bpy_object):
        return (
            bpy_object is not None
            and bpy_object.type == "MESH"
            and bpy_object.charon_forged.form in Forged._kinds
            and Group.PROP_GROUP_ID in bpy_object
        )

    @staticmethod
    def kind_of(bpy_object):
        return Forged._kinds.get(bpy_object.charon_forged.form)

    @staticmethod
    def is_triangle(settings):
        """Whether the part is laid as a triangle - as set, or as it was
        found to be when Part Shape is Auto."""
        if settings.part_shape == "AUTO":
            return settings.detected_shape == triangles.TRIANGLE
        return settings.part_shape == triangles.TRIANGLE

    # Measuring the part ---
    @staticmethod
    def part_to_surface(size, base=None):
        """The rotation from the part's own axes into the surface frame, the
        thinnest side facing out - a floor or panel lies flat on a surface.
        `base` is the axis a triangle's base runs along, which is turned to
        lie along the frame's x, the way its rows run."""
        face = min(range(3), key=lambda i: size[i])
        around, up = (face + 1) % 3, (face + 2) % 3
        flip = 1.0
        if base is not None and base != around:
            # the other way round, and one turned back to keep it a turn
            # rather than a mirror
            around, up, flip = up, around, -1.0
        columns = [None, None, None]
        columns[around] = Vector((1.0, 0.0, 0.0))
        columns[up] = Vector((0.0, flip, 0.0))
        columns[face] = Vector((0.0, 0.0, 1.0))
        return Matrix(columns).transposed()

    @staticmethod
    def _footprint_shape(mesh, size):
        """The part's triangle seen from above, if it is one: (the axis its
        base runs along, how far along the base its tip is, the axis and way
        its tip is from the base) - or None."""
        count = len(mesh.vertices)
        if count < 3:
            return None
        coords = np.empty(count * 3, dtype=np.float64)
        mesh.vertices.foreach_get("co", coords)
        coords = coords.reshape(-1, 3)
        face = min(range(3), key=lambda i: size[i])
        axes = ((face + 1) % 3, (face + 2) % 3)
        found = triangles.detect(coords[:, axes])
        if found is None:
            return None
        return axes[found.base_axis], found.tip, axes[1 - found.base_axis], found.side

    @staticmethod
    def measure(settings, mesh):
        """Store what a layout needs to know about the part: its footprint on
        a surface, how it turns onto one, and where its centre is."""
        size, centre = mesh_bounds(mesh)
        size = size * settings.base_scale
        shape = Forged._footprint_shape(mesh, size)
        settings.detected_shape = triangles.TRIANGLE if shape else triangles.RECTANGLE
        base = None
        if Forged.is_triangle(settings):
            if shape is None:
                # set to a triangle that wasn't found to be one: its base
                # along its longer side, its tip halfway
                face = min(range(3), key=lambda i: size[i])
                across = sorted(((face + 1) % 3, (face + 2) % 3), key=lambda i: -size[i])
                shape = (across[0], 0.5, across[1], 1.0)
            base, tip, tip_axis, tip_way = shape
        orientation = Forged.part_to_surface(size, base)
        settings.measured_shape = triangles.TRIANGLE if base is not None else triangles.RECTANGLE
        if base is not None:
            settings.triangle_tip = tip
            # which way the tip is along the frame's up
            settings.triangle_side = tip_way * orientation[1][tip_axis]
        extent = Vector([
            sum(abs(orientation[row][column]) * size[column] for column in range(3))
            for row in range(3)
        ])
        settings.part_size = size
        settings.pitch_around = max(extent.x, Forged.MIN_PITCH)
        settings.pitch_up = max(extent.y, Forged.MIN_PITCH)
        settings.base_rotation = (Forged.SURFACE_FRAME @ orientation).to_euler("XYZ")
        settings.centre_offset = Forged.SURFACE_FRAME @ orientation @ centre

    @staticmethod
    def _orientation(settings):
        """The part's rotation into a surface frame, before its local rotation."""
        base = Euler(settings.base_rotation, "XYZ").to_matrix()
        return Forged.SURFACE_FRAME.transposed() @ base

    @staticmethod
    def turn_and_centre(settings):
        """The part's rotation into a surface frame with its local rotation,
        and its centre in that frame - what frames.place takes.

        The local rotation turns each part about its own centre and nothing
        else: the layout is worked out for the part unturned (see
        footprint), so turning it never moves or adds a part.
        """
        orientation = Forged._orientation(settings)
        turn = orientation @ Euler(settings.rotation, "XYZ").to_matrix()
        centre = Forged.SURFACE_FRAME.transposed() @ Vector(settings.centre_offset)
        # the centre in the part's own axes, turned with it
        centre = turn @ (orientation.transposed() @ centre)
        return np.array(turn, dtype=np.float64), np.array(centre, dtype=np.float64)

    @staticmethod
    def footprint(settings):
        """How far the part reaches along a surface frame's x (along) and y
        (up), at its scale - unturned by its local rotation, so the layout
        stays put while it is turned."""
        size = np.array(settings.part_size, dtype=np.float64)
        if not size.any():
            # measured before its size was kept
            width, height = settings.pitch_around, settings.pitch_up
        else:
            orientation = np.array(Forged._orientation(settings), dtype=np.float64)
            extent = np.abs(orientation) @ size
            width, height = extent[0], extent[1]
        scale = settings.tile_scale
        return max(width, Forged.MIN_PITCH) * scale, max(height, Forged.MIN_PITCH) * scale

    @staticmethod
    def copy_scale(settings):
        return settings.base_scale * settings.tile_scale

    @staticmethod
    def as_triangles(settings, centres, normals, along, up, base=None):
        """A layout's frames with the copies a triangle part needs turned
        into the gaps along its rows - see objects/shapes/triangles.py. The
        frames as they were for any other part.

        `base` is each copy's base along its row, the part's at its scale
        if left out."""
        if not Forged.is_triangle(settings):
            return centres, normals, along, up
        if base is None:
            base = Forged.footprint(settings)[0]
        return triangles.interleave(centres, normals, along, up, base,
                                    settings.triangle_tip)[:4]

    # For each kind ---
    @classmethod
    def initialise(cls, settings):
        """Starting settings for a new object, once the part is measured."""

    @classmethod
    def compute(cls, settings):
        """Lay the copies out.

        Returns:
            (positions, rotations, settings to write once it is accepted),
            and optionally each copy's size against the rest - 1 for all of
            them if left out

        Raises:
            LayoutRefused: when it can't be built.
        """
        raise NotImplementedError

    # Node tree ---
    @staticmethod
    def _node_group(modifier):
        """The object's own tree for its modifier: the part on each point,
        turned by the point's rotation and scaled by its scale.

        The part is set on the tree's node rather than as a modifier input -
        Blender 5.2 has no ID properties on modifiers to hold it in - so
        every object keeps a tree of its own. A tree
        shared, by an object duplicated or one made before this, is replaced.
        """
        tree = modifier.node_group
        if (
            tree is not None
            and tree.users == 1
            and tree.get("charon_version") == Forged.NODE_GROUP_VERSION
            and Forged.PART_NODE in tree.nodes
            and Forged.COPIES_NODE in tree.nodes
        ):
            return tree
        tree = bpy.data.node_groups.new(Forged.NODE_GROUP, "GeometryNodeTree")

        interface = tree.interface
        interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

        nodes, links = tree.nodes, tree.links
        group_input = nodes.new("NodeGroupInput")
        part = nodes.new("GeometryNodeObjectInfo")
        part.name = Forged.PART_NODE
        part.transform_space = "ORIGINAL"
        rotation = nodes.new("GeometryNodeInputNamedAttribute")
        rotation.data_type = "QUATERNION"
        rotation.inputs["Name"].default_value = Forged.ROTATION_ATTRIBUTE
        size = nodes.new("GeometryNodeInputNamedAttribute")
        size.data_type = "FLOAT"
        size.inputs["Name"].default_value = Forged.SCALE_ATTRIBUTE
        instances = nodes.new("GeometryNodeInstanceOnPoints")
        instances.name = Forged.COPIES_NODE
        group_output = nodes.new("NodeGroupOutput")

        rotation_output, size_output = (
            next(
                (socket for socket in node.outputs
                 if socket.name == "Attribute" and socket.enabled),
                node.outputs[0],
            )
            for node in (rotation, size)
        )
        links.new(group_input.outputs["Geometry"], instances.inputs["Points"])
        links.new(part.outputs["Geometry"], instances.inputs["Instance"])
        links.new(rotation_output, instances.inputs["Rotation"])
        links.new(size_output, instances.inputs["Scale"])
        links.new(instances.outputs["Instances"], group_output.inputs["Geometry"])

        group_input.location = (0, 0)
        part.location = (220, -60)
        rotation.location = (220, -260)
        size.location = (220, -420)
        instances.location = (440, 0)
        group_output.location = (660, 0)

        tree["charon_version"] = Forged.NODE_GROUP_VERSION
        return tree

    @staticmethod
    def _set_part(forged_obj, part):
        modifier = forged_obj.modifiers.get(Forged.MODIFIER)
        if modifier is None:
            modifier = forged_obj.modifiers.new(Forged.MODIFIER, "NODES")
        tree = Forged._node_group(modifier)
        changed = modifier.node_group is not tree
        if changed:
            old_tree = modifier.node_group
            modifier.node_group = tree
            if old_tree is not None and old_tree.users == 0:
                bpy.data.node_groups.remove(old_tree)

        part_socket = tree.nodes[Forged.PART_NODE].inputs["Object"]
        if part_socket.default_value != part:
            part_socket.default_value = part
            changed = True
        return changed

    @staticmethod
    def _own_mesh(forged_obj):
        """The object's mesh, copied off first when it shares it - a Shift+D
        duplicate shares its mesh with the original, and laying one out again
        would move the copies of both. The first change sets them apart."""
        mesh = forged_obj.data
        if mesh.users > 1:
            mesh = mesh.copy()
            forged_obj.data = mesh
        return mesh

    @staticmethod
    def _write_points(mesh, positions, rotations, scales):
        mesh.clear_geometry()
        mesh.vertices.add(len(positions))
        mesh.vertices.foreach_set("co", positions.astype(np.float32).ravel())
        attribute = mesh.attributes.get(Forged.ROTATION_ATTRIBUTE)
        if attribute is None:
            attribute = mesh.attributes.new(Forged.ROTATION_ATTRIBUTE, "QUATERNION", "POINT")
        attribute.data.foreach_set(
            "value", frames.to_quaternions(rotations).astype(np.float32).ravel()
        )
        attribute = mesh.attributes.get(Forged.SCALE_ATTRIBUTE)
        if attribute is None:
            attribute = mesh.attributes.new(Forged.SCALE_ATTRIBUTE, "FLOAT", "POINT")
        attribute.data.foreach_set("value", np.asarray(scales, dtype=np.float32).ravel())
        mesh.update()

    # Objects ---
    @classmethod
    def create(cls, source):
        """Turn a part into one of these, in its place.

        Returns:
            bpy.types.Object: The new object.
        """
        part_mesh = source.data
        object_id = source[Part.PROP_OBJECT_ID].replace("^", "")
        user_data = source.get(Part.PROP_USER_DATA, Part.DEFAULT_USER_DATA)
        name = "%s %s" % (object_id, cls.LABEL)

        # in no scene: only the modifier reads it
        holder = bpy.data.objects.new("%s Part" % name, part_mesh)

        # the colour tools read the part id off the mesh, the way they do a
        # group's
        points = bpy.data.meshes.new(name)
        points[MESH_TAG] = object_id
        forged_obj = bpy.data.objects.new(name, points)
        for collection in source.users_collection:
            collection.objects.link(forged_obj)
        if not forged_obj.users_collection:
            bpy.context.scene.collection.objects.link(forged_obj)
        forged_obj.matrix_world = Matrix.Translation(source.matrix_world.translation)

        # the colour the part had
        for key in source.keys():
            if key.startswith("nms_"):
                forged_obj[key] = source[key]
        forged_obj.color = source.color
        forged_obj[Part.PROP_USER_DATA] = str(user_data)

        forged_obj[Group.PROP_GROUP_ID] = str(uuid.uuid4())
        forged_obj[Group.PROP_IS_MIRROR] = False
        forged_obj[Group.PROP_ORIGIN_OFFSET] = (0.0, 0.0, 0.0)
        forged_obj[Group.PROP_CHILD_CACHE] = "{}"

        settings = forged_obj.charon_forged
        scale = source.matrix_world.to_scale()
        with Forged.suspended():
            settings.form = cls.FORM
            settings.part_object = holder
            settings.object_id = object_id
            settings.base_scale = (abs(scale.x) + abs(scale.y) + abs(scale.z)) / 3 or 1.0
            Forged.measure(settings, part_mesh)
            cls.initialise(settings)

        bpy.data.objects.remove(source, do_unlink=True)
        Forged.update(forged_obj)
        return forged_obj

    @staticmethod
    def update(forged_obj):
        """Lay the object out again from its settings. A refused layout
        leaves it, and what it exports, as it was."""
        settings = forged_obj.charon_forged
        kind = Forged.kind_of(forged_obj)
        holder = settings.part_object
        if kind is None:
            return
        if holder is None or holder.data is None:
            settings.message = "The part is gone"
            return

        # measured again when the part is to be laid as another shape than
        # it was - or when it was measured before shapes were told apart
        shape = triangles.TRIANGLE if Forged.is_triangle(settings) else triangles.RECTANGLE
        if not settings.detected_shape or settings.measured_shape != shape:
            with Forged.suspended():
                Forged.measure(settings, holder.data)

        try:
            positions, rotations, accepted, *sizes = kind.compute(settings)
            if len(positions) > Forged.MAX_PARTS:
                raise LayoutRefused(
                    "%d parts, the most is %d" % (len(positions), Forged.MAX_PARTS)
                )
        except LayoutRefused as refusal:
            settings.message = str(refusal)
            return

        settings.message = ""
        settings.part_count = len(positions)
        # on the object too, where a group keeps its size - what the
        # Watchtower's part count adds up
        forged_obj[Group.PROP_PART_COUNT] = len(positions)
        scale = Forged.copy_scale(settings)
        with Forged.suspended():
            settings.applied_scale = scale
            for name, value in accepted.items():
                setattr(settings, name, value)

        sizes = sizes[0] if sizes else np.ones(len(positions))
        Forged._write_points(Forged._own_mesh(forged_obj), positions, rotations, scale * sizes)
        if Forged._set_part(forged_obj, holder):
            # values written from Python don't always tag the object themselves
            forged_obj.update_tag()

    # Exporting ---
    @staticmethod
    def local_matrices(forged_obj):
        """Every copy's matrix relative to the object, read off the points it
        shows - so what exports is always what is on screen."""
        mesh = forged_obj.data
        count = len(mesh.vertices)
        positions = np.empty(count * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", positions)
        quaternions = np.zeros(count * 4, dtype=np.float32)
        attribute = mesh.attributes.get(Forged.ROTATION_ATTRIBUTE)
        if attribute is not None and count:
            attribute.data.foreach_get("value", quaternions)

        scales = np.full(count, forged_obj.charon_forged.applied_scale, dtype=np.float32)
        attribute = mesh.attributes.get(Forged.SCALE_ATTRIBUTE)
        if attribute is not None and count:
            attribute.data.foreach_get("value", scales)

        matrices = np.zeros((count, 4, 4))
        if count:
            rotations = frames.from_quaternions(quaternions.reshape(-1, 4))
            matrices[:, :3, :3] = rotations * scales[:, None, None]
            matrices[:, :3, 3] = positions.reshape(-1, 3)
            matrices[:, 3, 3] = 1.0
        return matrices

    @staticmethod
    def get_all():
        """Every forged object in the view layer."""
        found = []
        for obj in bpy.context.view_layer.objects:
            try:
                if Forged.is_forged(obj):
                    found.append(obj)
            except ReferenceError:
                continue
        return found

    @staticmethod
    def serialise(forged_obj):
        """The object as the parts it stands for, in the form NMS saves them.

        Returns:
            List of serialised part dictionaries.
        """
        settings = forged_obj.charon_forged
        object_id = f"^{settings.object_id}"
        user_data = int(forged_obj.get(Part.PROP_USER_DATA, Part.DEFAULT_USER_DATA))
        time_stamp = int(time.time())
        world = np.array(forged_obj.matrix_world, dtype=np.float64)

        serialised_objects = []
        for matrix in world @ Forged.local_matrices(forged_obj):
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
    def refresh_child_cache(forged_obj):
        """Write the object's child cache - what the group code reads when it
        splits it or looks up its colour."""
        settings = forged_obj.charon_forged
        matrices = Forged.local_matrices(forged_obj)

        user_data = forged_obj.get(Part.PROP_USER_DATA, Part.DEFAULT_USER_DATA)
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
        forged_obj[Group.PROP_CHILD_CACHE] = json.dumps(cache)
        forged_obj[Group.PROP_PART_COUNT] = len(matrices)
        forged_obj[Group.PROP_ORIGIN_MATRIX] = json.dumps(
            [list(row) for row in forged_obj.matrix_world]
        )

    @staticmethod
    def split(forged_obj, builder):
        """Turn the object into its parts. Returns them."""
        holder = forged_obj.charon_forged.part_object
        Forged.refresh_child_cache(forged_obj)
        with Forged.suspended():
            forged_obj.charon_forged.form = ""
        # one texture and node group tidy for the lot, not one per part
        with materials.defer_shared_data():
            parts = Group.ungroup_objects(builder, forged_obj) or []
        if holder is not None and holder.users == 0:
            bpy.data.objects.remove(holder)
        return parts
