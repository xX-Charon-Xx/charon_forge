"""Fast bulk import of the parts in NMS base data.

The import collection is excluded from the view layer while parts are created,
and as much data as possible is shared between the objects made:

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


def import_objects(builder_object, objects_data, compensate_normal=True, high_res=True):
    """Build every part in a save's "Objects" list.

    Args:
        builder_object: The builder the parts belong to.
        objects_data (list): The part dictionaries out of the save.
        compensate_normal (bool): Passed to override classes, see BaseVersion.
        high_res (bool): False to build every part from the fbx proxies.
    """
    # High res meshes, keyed by object id. Shared by every placement.
    unique_meshes = {}
    # Fbx fallback objects and their per (object id, user data) mesh copies.
    unique_objects = {}
    unique_materials = {}
    # (object, user data) pairs to colour in one pass at the end.
    to_colour = []

    asset_index = asset_library.get_asset_index() if high_res else {}
    timing = {"start": time.perf_counter()}
    asset_library.reset_load_stats()

    # exclude the collection from the view layer, so creating objects doesn't
    # update the scene after every disk read or new object
    import_collection = collection_utils.get_collection(IMPORT_COLLECTION_NAME)
    collection_utils.set_collection_visibility(import_collection.name, visible=False)

    # a bad part must never leave the collection excluded - that would look
    # like the import silently did nothing
    try:
        # local lookups, this loop runs once per placed part
        link_object = import_collection.objects.link
        new_object = bpy.data.objects.new

        for order, part_data in enumerate(objects_data):
            raw_object_id = part_data.get(Part.PROP_OBJECT_ID, None)
            if raw_object_id is None:
                continue

            object_id = raw_object_id.replace("^", "")
            user_data = part_data.get(Part.PROP_USER_DATA, 0)

            # parts with a class of their own are left to it
            override_class = placement.get_override_class(builder_object, object_id)
            if override_class is not None:
                override_class.deserialise_from_data(
                    part_data, builder_object, compensate_normal=compensate_normal
                )
                continue

            # import object_id from disk when visiting it first time
            if object_id not in unique_meshes:
                unique_meshes[object_id] = (
                    asset_library.load_high_res_mesh(object_id, asset_index)
                    if high_res else None
                )
            high_res_mesh = unique_meshes[object_id]

            if high_res_mesh is not None:
                # a plain new object over the cached mesh - no copy, no ops,
                # and every instance of this id points at the same mesh
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

        # colour every high res part in one pass, then dedupe so the shared
        # materials are the ones that get prepared (glow wired, old finish
        # nodes out)
        materials.apply_many(to_colour)
        timing["colour"] = time.perf_counter()
        materials.dedupe_appended_data()
        timing["dedupe"] = time.perf_counter()
        materials.prepare_materials()
        materials.use_object_colour_in_viewport()
        timing["prepare"] = time.perf_counter()

    finally:
        collection_utils.set_collection_visibility(import_collection.name, visible=True)
        bpy.context.view_layer.update()

    timing["end"] = time.perf_counter()
    if REPORT_TIMING:
        _report_timing(len(objects_data), timing)


def _report_timing(part_count, timing):
    """One console line saying where an import's time went.

    The asset stages (append, clean, glow) happen inside the build loop the
    first time each id is met, so they are shown as part of it.
    """
    stats = asset_library.get_load_stats()
    start = timing["start"]

    def span(first, last):
        if first not in timing or last not in timing:
            return "-"
        return "%.2fs" % (timing[last] - timing[first])

    print(
        "Charon Forge: imported %d parts in %.2fs - build %s (%d new assets: "
        "append %.2fs, clean %.2fs, glow %.2fs), colour %s, dedupe %s, "
        "prepare %s, scene update %s"
        % (
            part_count, timing["end"] - start, span("start", "build"),
            stats["assets"], stats["append"], stats["clean"], stats["glow"],
            span("build", "colour"), span("colour", "dedupe"),
            span("dedupe", "prepare"), span("prepare", "end"),
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
