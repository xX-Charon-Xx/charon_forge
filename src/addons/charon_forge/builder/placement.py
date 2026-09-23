"""Turning library meshes into placed parts.

Everything here works against any builder - Charon Forge's own, or the base
builder addon's - through the handful of methods every builder has:
get_part_class(), add_to_part_cache() and add_part(). The Part class a new
object is wrapped in is always the builder's own, so the parts that come back
are the ones that builder's operators and panels expect.
"""

import time

import bpy

from ..objects.part import Part
from .. import materials
from ..utils.base_builder_utils import blend_utils
from . import asset_library, proxy_library

# Every builder's get_part_class() falls back to its plain Part class for an id
# with no override class. No part has an empty id, so asking for "" is how the
# plain Part class is found without knowing which addon the builder is from.
_NO_OVERRIDE_ID = ""


def get_default_part_class(builder_object):
    """The builder's plain Part class."""
    return builder_object.get_part_class(_NO_OVERRIDE_ID)


def get_override_class(builder_object, object_id):
    """The builder's special class for this id, or None for a plain part."""
    part_class = builder_object.get_part_class(object_id)
    if part_class is get_default_part_class(builder_object):
        return None
    return part_class


def new_high_res_object(object_id, asset_index=None):
    """Make a bare object over the shared high res mesh for an id.

    Everything the high res library places goes through here, including the
    fossil bones, which build their own object rather than going through
    add_part - see nms/part_overrides/bone.py.

    No properties are set and nothing is coloured; that is the caller's job.

    Returns:
        bpy.types.Object: The new object, or None when the library doesn't
            cover the id, so the caller can fall back to the fbx proxy.
    """
    mesh = asset_library.load_high_res_mesh(object_id, asset_index)
    if mesh is None:
        return None

    # a plain new object over the shared mesh - adding the tenth copy of a part
    # costs an object datablock and nothing else
    bpy_object = bpy.data.objects.new(object_id, mesh)
    blend_utils.add_to_scene(bpy_object)
    return bpy_object


def stamp_part_properties(bpy_object, object_id, part_class):
    """Write the properties a builder reads a new part back by."""
    bpy_object.hide_select = False
    bpy_object[part_class.PROP_OBJECT_ID] = object_id
    bpy_object[part_class.PROP_SNAP_ID] = object_id
    bpy_object[part_class.PROP_TIMESTAMP] = str(int(time.time()))
    bpy_object[part_class.PROP_BELONGS_TO_PRESET] = part_class.DEFAULT_BELONGS_TO_PRESET
    bpy_object[part_class.PROP_ORDER] = len(bpy.data.objects)


def _add_proxy_part(builder_object, object_id, user_data, build_rigs):
    # a builder carrying HighResBuilderMixin has add_part pointing back here, so
    # its base class's own add_part is reached through add_proxy_part instead
    add = getattr(builder_object, "add_proxy_part", builder_object.add_part)
    return add(object_id, user_data=user_data, build_rigs=build_rigs)


def add_part(builder_object, object_id, user_data=None, build_rigs=True, high_res=True):
    """Add a single part, the way the asset browser and the build tools do it.

    Hands back the builder's own Part wrapper, so .object, .select(),
    .snap_to() and .build_rig() all still work on the result.

    Args:
        builder_object: The builder the part belongs to.
        object_id (str): The part to build.
        user_data: The packed UserData value, or None for the part default.
        build_rigs (bool): Passed through to the part class.
        high_res (bool): True to place the high res asset when the id has one,
            False to always place the builder's own fbx proxy instead.

    Returns:
        Part: The new part.
    """
    object_id = object_id.replace("^", "")

    # matched before the part exists, so a new part lands on whatever was
    # selected rather than on itself
    active_object = bpy.context.active_object

    # Parts with a class of their own need it whether or not the caller asked
    # for the high res library, so they are checked first - and built by that
    # class, the same one deserialising a save uses.
    override_class = get_override_class(builder_object, object_id)
    if override_class is not None:
        item = override_class(
            object_id=object_id,
            builder_object=builder_object,
            user_data=user_data,
            build_rigs=build_rigs,
        )
        if active_object is not None:
            item.object.matrix_world = active_object.matrix_world.copy()
        return item

    # ids the high res library doesn't cover fall back to the proxy too
    bpy_object = new_high_res_object(object_id) if high_res else None
    if bpy_object is None:
        return _add_proxy_part(builder_object, object_id, user_data, build_rigs)

    part_class = get_default_part_class(builder_object)
    stamp_part_properties(bpy_object, object_id, part_class)

    # colour by object property, so this placement goes on sharing the mesh.
    # A new part gets what the game gives it: its own default palette and
    # finish, not palette 0 - a corvette part is BIGGS0, a station part
    # STATION0.
    if user_data is None:
        user_data = materials.default_user_data(object_id)
    materials.recolour_from_user_data([bpy_object], user_data)

    # if the asset was appended just now it brought its own copies of textures
    # and of the colourise node group with it. Cheap to call either way - with
    # nothing to collapse this is a scan of bpy.data.images, and materials
    # already prepared are skipped by their tag
    materials.dedupe_appended_data()
    materials.prepare_materials(bpy_object.data.materials)

    item = part_class(
        bpy_object=bpy_object, builder_object=builder_object, build_rigs=build_rigs
    )
    item.reset_transforms()

    if active_object is not None:
        item.object.matrix_world = active_object.matrix_world.copy()

    return item


def new_merge_source(object_id, user_data, high_res=True, proxy_cache=None, catalog=None):
    """Make a bare part object for something that is about to be merged away.

    Rebuilding a group places every child of it only to join them into one mesh
    and throw the children away, so nothing add_part() does around the object
    itself - the part class, the rig, the snapping metadata, the palette
    properties - survives long enough to be read. What does survive the merge
    is the geometry, the material slots and the ObjectID and UserData
    properties, so those are all this sets.

    Falls back to the other library when the requested one has no model for the
    id, the same way add_part() does, so a group is never rebuilt with holes in
    it.

    Returns:
        bpy.types.Object: The new object, or None when neither library covers
            the id.
    """
    if high_res:
        bpy_object = new_high_res_object(object_id)
        if bpy_object is None:
            bpy_object = proxy_library.new_proxy_object(
                object_id, user_data, cache=proxy_cache, catalog=catalog
            )
    else:
        bpy_object = proxy_library.new_proxy_object(
            object_id, user_data, cache=proxy_cache, catalog=catalog
        )
        if bpy_object is None:
            bpy_object = new_high_res_object(object_id)

    if bpy_object is None:
        return None

    # property names are the same in every builder's Part class
    bpy_object[Part.PROP_OBJECT_ID] = object_id
    bpy_object[Part.PROP_USER_DATA] = str(
        user_data if user_data is not None else Part.DEFAULT_USER_DATA
    )
    return bpy_object
