"""Fast bulk import of the parts in NMS base data.

An import runs in batches, each a single pass over the whole base: every
asset the base needs is appended first, then every object is made, then every
part is coloured, then the materials the appends brought in are deduped and
prepared once - see import_objects. The import collection is excluded from
the view layer throughout, and as much data as possible is shared between the
objects made:

- Parts from the high res library share ONE mesh datablock (and with it one
  set of materials) across every placement of that object id, whatever their
  UserData, because colour lives on the object as custom properties rather
  than on the material - see materials/colouring.py.
- Parts that fall back to the builder's fbx proxy keep the old behaviour,
  where the mesh has to be copied per (ObjectID, UserData) pair because the
  colour is baked into a flat material.

Works against any builder, see placement.py.
"""

import math
import time

import bpy
import mathutils

from ..objects.part import Part
from .. import materials
from ..utils import collection_utils
from . import asset_library, placement

# name of collection to import objects to
IMPORT_COLLECTION_NAME = "Collection"

# Print where each import's time went to the console - see _report_timing.
REPORT_TIMING = True

# This is to compensate blender's Z up axis.
X_ROT_90 = mathutils.Matrix.Rotation(math.radians(90.0), 4, "X")


# what marks an object as part of a build: parts, line points, presets,
# groups (Forge shapes too), power line controls and curves carrying parts
BUILD_PROPS = ("ObjectID", "SnapID", "PresetID", "GroupID", "rig_item",
               "has_linked_objects", "curve_parent")


def clear_scene_parts(scene=None):
    """Remove everything buildable from the scene, before a ship is imported
    into it - so the import is the ship and nothing left over from before.

    Anything else - lights, cameras, a space station built by The Forge -
    is left alone. The library meshes stay cached in bpy.data, so importing
    the same parts again doesn't read them off disk.

    Returns:
        int: How many objects were removed.
    """
    scene = scene or bpy.context.scene
    doomed = set()
    holders = set()
    # Object.children_recursive walks every object in the file on each call,
    # so asking it once per part made clearing a 2700 part ship take 0.7s -
    # one map of who parents whom is built here instead
    children = {}
    for obj in bpy.data.objects:
        if obj.parent is not None:
            children.setdefault(obj.parent, []).append(obj)
    for obj in scene.objects:
        if not any(prop in obj for prop in BUILD_PROPS):
            continue
        doomed.add(obj)
        stack = list(children.get(obj, ()))
        while stack:
            child = stack.pop()
            if child not in doomed:
                doomed.add(child)
                stack.extend(children.get(child, ()))
        # a Forge shape's part sits on a holder object in no scene
        forged = getattr(obj, "charon_forged", None)
        holder = getattr(forged, "part_object", None) if forged is not None else None
        if holder is not None:
            holders.add(holder)

    if doomed:
        bpy.data.batch_remove(list(doomed))
    unused_holders = [holder for holder in holders if holder.users == 0]
    if unused_holders:
        bpy.data.batch_remove(unused_holders)
    return len(doomed)


def import_objects(builder_object, objects_data, compensate_normal=True, high_res=True):
    """Build every part in a save's "Objects" list.

    Args:
        builder_object: The builder the parts belong to.
        objects_data (list): The part dictionaries out of the save.
        compensate_normal (bool): Passed to override classes, see BaseVersion.
        high_res (bool): False to build every part from the fbx proxies.
    """
    # Fbx fallback objects and their per (object id, user data) mesh copies.
    unique_objects = {}
    unique_materials = {}
    # (object, user data) pairs to colour in one pass at the end.
    to_colour = []

    timing = {"start": time.perf_counter()}
    asset_library.reset_load_stats()

    # what each part is, worked out once: (order, data, id, user data, the
    # class that builds it when it has one of its own)
    parts = []
    for order, part_data in enumerate(objects_data):
        raw_object_id = part_data.get(Part.PROP_OBJECT_ID, None)
        if raw_object_id is None:
            continue
        object_id = raw_object_id.replace("^", "")
        parts.append((
            order, part_data, object_id,
            part_data.get(Part.PROP_USER_DATA, 0),
            placement.get_override_class(builder_object, object_id),
        ))

    # the collection is out of the view layer while it fills, so creating
    # objects doesn't update the scene after every disk read or new object;
    # it is put back even when a part fails, and always included at the end
    # - an import that stays excluded looks like it did nothing
    import_collection = collection_utils.get_collection(IMPORT_COLLECTION_NAME)
    try:
        with collection_utils.excluded_from_view_layer(import_collection):
            # the whole-library material passes - dedupe, glow, tint - are
            # wanted by every append and by parts with classes of their own;
            # inside this they run once, when it closes
            with materials.defer_shared_data():
                # 1. every asset, in one batch: each id's shared mesh, and
                # its materials merged into the ones the file already has
                unique_meshes = (
                    asset_library.load_high_res_meshes(
                        [part[2] for part in parts if part[4] is None]
                    )
                    if high_res else {}
                )
                timing["assets"] = time.perf_counter()

                # 2. every object, a plain new one over its id's shared mesh -
                # no copy, no ops, every placement of an id on the one mesh
                link_object = import_collection.objects.link
                new_object = bpy.data.objects.new
                for order, part_data, object_id, user_data, override_class in parts:
                    if override_class is not None:
                        override_class.deserialise_from_data(
                            part_data, builder_object, compensate_normal=compensate_normal
                        )
                        continue

                    high_res_mesh = unique_meshes.get(object_id)
                    if high_res_mesh is not None:
                        bpy_object = new_object(object_id, high_res_mesh)
                        link_object(bpy_object)
                        to_colour.append((bpy_object, user_data))
                    else:
                        bpy_object = build_fbx_part(
                            builder_object,
                            object_id,
                            user_data,
                            import_collection,
                            unique_objects,
                            unique_materials,
                        )
                        if bpy_object is None:
                            continue

                    restore_params(bpy_object, part_data, object_id)
                    bpy_object.matrix_world = deserialise_matrix_world(part_data)
                    bpy_object[Part.PROP_ORDER] = order
                timing["build"] = time.perf_counter()

                # 3. every high res part coloured in one pass - properties on
                # the objects, so the materials stay shared
                materials.apply_many(to_colour, fresh=True)
                timing["colour"] = time.perf_counter()

                # asked for here, so they run on leaving even when every
                # asset was already in the file
                materials.dedupe_appended_data()
                materials.prepare_materials()

            # 4. leaving the block ran the material passes once: textures and
            # node groups the appends duplicated collapsed first, so the
            # shared materials are the ones that get prepared
            materials.use_object_colour_in_viewport()
            timing["materials"] = time.perf_counter()

    finally:
        collection_utils.set_collection_visibility(import_collection.name, visible=True)
        bpy.context.view_layer.update()

    timing["end"] = time.perf_counter()
    if REPORT_TIMING:
        _report_timing(len(objects_data), timing)


def _report_timing(part_count, timing):
    """One console line saying where an import's time went."""
    stats = asset_library.get_load_stats()
    start = timing["start"]

    def span(first, last):
        if first not in timing or last not in timing:
            return "-"
        return "%.2fs" % (timing[last] - timing[first])

    print(
        "Charon Forge: imported %d parts in %.2fs - assets %s (%d new: "
        "append %.2fs, merge %.2fs, clean %.2fs, glow %.2fs), build %s, "
        "colour %s, materials %s, scene update %s"
        % (
            part_count, timing["end"] - start, span("start", "assets"),
            stats["assets"], stats["append"], stats["merge"], stats["clean"], stats["glow"],
            span("assets", "build"), span("build", "colour"),
            span("colour", "materials"), span("materials", "end"),
        )
    )


# colour is a flat material on the mesh, so objects can only share a mesh when
# their ObjectID AND UserData match
def build_fbx_part(
    builder_object, object_id, user_data, import_collection, unique_objects, unique_materials
):
    material_key = (object_id, user_data)

    # import object from disk when visiting that object_id for first time
    if object_id not in unique_objects:
        bpy_object = import_fbx_from_disk(builder_object, object_id)
        if bpy_object is None:
            return None

        collection_utils.move_object_into_collection(import_collection, bpy_object)
        materials.restore_material(bpy_object, user_data)
        builder_object.add_to_part_cache(object_id, bpy_object)

        unique_objects[object_id] = bpy_object
        unique_materials[material_key] = bpy_object.data
        return bpy_object

    # a copy of the one already imported, sharing its mesh when the colour
    # matches too
    bpy_object = unique_objects[object_id].copy()
    import_collection.objects.link(bpy_object)

    if material_key in unique_materials:
        bpy_object.data = unique_materials[material_key]
    else:
        bpy_object.data = bpy_object.data.copy()
        materials.restore_material(bpy_object, user_data)
        unique_materials[material_key] = bpy_object.data

    return bpy_object


def import_fbx_from_disk(builder_object, object_id):
    """Import an id's fbx, or make a cube stand-in when it has none."""
    fbx_path = builder_object.get_obj_path(object_id)

    objects_before = set(bpy.data.objects)
    try:
        if fbx_path is None:
            bpy.ops.mesh.primitive_cube_add()
        else:
            bpy.ops.import_scene.fbx(filepath=fbx_path)
    except RuntimeError:
        pass
    new_objects = [item for item in bpy.data.objects if item not in objects_before]

    if not new_objects:
        # the cube op fails while the active collection is excluded
        if fbx_path is not None:
            return None
        bpy_object = bpy.data.objects.new(object_id, bpy.data.meshes.new(object_id))
    else:
        bpy_object = next(
            (item for item in new_objects if item.type == "MESH"), new_objects[0]
        )

    bpy_object.name = object_id
    if bpy_object.data is not None:
        bpy_object.data.materials.clear()

    try:
        bpy_object.select_set(False)
    except RuntimeError:
        pass

    return bpy_object


def restore_params(bpy_object, part_data, object_id):
    """Copy the part properties out of its save data onto the object."""
    user_data = part_data.get(Part.PROP_USER_DATA, "")
    time_stamp = str(part_data.get(Part.PROP_TIMESTAMP, int(time.time())))
    message = part_data.get(Part.PROP_MESSAGE, None)

    bpy_object[Part.PROP_OBJECT_ID] = object_id
    bpy_object[Part.PROP_SNAP_ID] = object_id
    bpy_object[Part.PROP_USER_DATA] = str(user_data)
    bpy_object[Part.PROP_TIMESTAMP] = time_stamp
    bpy_object[Part.PROP_BELONGS_TO_PRESET] = False

    # copies carry the source's message, so clear it when this part has none
    if message:
        bpy_object[Part.PROP_MESSAGE] = message
    else:
        bpy_object.pop(Part.PROP_MESSAGE, None)

    return bpy_object


def deserialise_matrix_world(part_data):
    """The world matrix out of a part's Position, Up and At."""
    pos = part_data.get("Position", [0.0, 0.0, 0.0])
    up = part_data.get("Up", [0.0, 0.0, 0.0])
    at = part_data.get("At", [0.0, 0.0, 0.0])
    return create_matrix_from_vectors(pos, up, at)


def create_matrix_from_vectors(pos, up, at):
    """Create a world space matrix given by an Up and At vector.

    Args:
        pos (list): 3 element list/vector representing the x,y,z position.
        up (list): 3 element list/vector representing the up vector.
        at (list): 3 element list/vector representing the aim vector.
    """
    up_vector = mathutils.Vector(up)
    at_vector = mathutils.Vector(at)

    # Compute right vector and normalize
    right_vector = at_vector.cross(up_vector)
    right_vector.normalize()
    right_vector *= -1

    # Get the up length once
    up_length = up_vector.length
    right_vector.length = up_length
    at_vector.length = up_length

    mat = mathutils.Matrix((
        (right_vector[0], up_vector[0], at_vector[0], pos[0]),
        (right_vector[1], up_vector[1], at_vector[1], pos[1]),
        (right_vector[2], up_vector[2], at_vector[2], pos[2]),
        (0.0, 0.0, 0.0, 1.0),
    ))

    return X_ROT_90 @ mat
