"""Turning library meshes into placed parts, for any builder (Charon's or the base
builder addon's), always wrapped in that builder's own Part class."""

import time

import bpy
from mathutils import Euler, Matrix

from ..objects.part import Part
from .. import materials
from ..utils import dictionary, loading_overlay
from ..utils.base_builder_utils import blend_utils
from . import asset_library, proxy_library

# No part has an empty id, so get_part_class("") returns the builder's plain
# Part class whichever addon it's from.
_NO_OVERRIDE_ID = ""


# A fossil bone's ObjectID is only its kind (FOS_SKULL...); the model it
# shows is in its Message.
FOSSIL_PREFIX = "FOS_"


def model_id_of(object_id, message=None):
    """The model a part shows: its ObjectID, or a fossil bone's Message."""
    stripped = str(object_id or "").replace("^", "")
    if message and stripped.startswith(FOSSIL_PREFIX):
        return str(message).replace("^", "")
    return stripped


# The rotation every part starts with: Y-up models turned 90 degrees about X.
DEFAULT_ROTATION = Euler((1.5708, 0.0, 0.0), "XYZ")


def new_part_matrix(context=None):
    """World matrix for a new part: on the active object if selected, else at the 3D
    cursor. Also works from timer contexts that have no active_object."""
    context = context or bpy.context
    scene = getattr(context, "scene", None) or bpy.data.scenes[0]
    view_layer = getattr(context, "view_layer", None) or scene.view_layers[0]

    active_object = getattr(context, "active_object", None)
    if active_object is None:
        active_object = view_layer.objects.active
    try:
        selected = active_object is not None and active_object.select_get(view_layer=view_layer)
    except RuntimeError:
        # not in this view layer
        selected = False
    if selected:
        return active_object.matrix_world.copy()
    return Matrix.Translation(scene.cursor.location) @ DEFAULT_ROTATION.to_matrix().to_4x4()


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
    """A bare, uncoloured object over the shared high res mesh for an id.
    None when the library doesn't cover the id, so the caller can use the proxy."""
    # every one-at-a-time placement comes through here
    loading_overlay.step()
    mesh = asset_library.load_high_res_mesh(object_id, asset_index)
    if mesh is None:
        return None

    # a plain object over the shared mesh, so extra copies cost almost nothing
    bpy_object = bpy.data.objects.new(object_id, mesh)
    blend_utils.add_to_scene(bpy_object)
    return bpy_object


def upgrade_to_high_res(bpy_object):
    """Swap a part built by its own class (fbx proxy or cube) to the high res mesh,
    like Fix Proxies does. True when the mesh was swapped."""
    if bpy_object is None or bpy_object.type != "MESH":
        return False
    if Part.PROP_OBJECT_ID not in bpy_object or materials.is_high_res(bpy_object):
        return False

    model_id = bpy_object.get("nms_form_model") or model_id_of(
        bpy_object[Part.PROP_OBJECT_ID], bpy_object.get(Part.PROP_MESSAGE)
    )
    mesh = asset_library.load_high_res_mesh(model_id)
    if mesh is None:
        return False

    old_mesh = bpy_object.data
    bpy_object.data = mesh
    if old_mesh is not None and old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)

    user_data = bpy_object.get(Part.PROP_USER_DATA)
    try:
        user_data = int(user_data)
    except (TypeError, ValueError):
        user_data = materials.default_user_data(model_id)
    materials.recolour_from_user_data([bpy_object], user_data)
    materials.dedupe_appended_data()
    materials.prepare_materials(mesh.materials)
    return True


def stamp_part_properties(bpy_object, object_id, part_class):
    """Write the properties a builder reads a new part back by."""
    bpy_object.hide_select = False
    bpy_object[part_class.PROP_OBJECT_ID] = object_id
    bpy_object[part_class.PROP_SNAP_ID] = object_id
    bpy_object[part_class.PROP_TIMESTAMP] = str(int(time.time()))
    bpy_object[part_class.PROP_BELONGS_TO_PRESET] = part_class.DEFAULT_BELONGS_TO_PRESET
    bpy_object[part_class.PROP_ORDER] = len(bpy.data.objects)


def _add_proxy_part(builder_object, object_id, user_data, build_rigs):
    # with HighResBuilderMixin, add_part points back here, so use add_proxy_part
    add = getattr(builder_object, "add_proxy_part", builder_object.add_part)
    return add(object_id, user_data=user_data, build_rigs=build_rigs)


def add_part(builder_object, object_id, user_data=None, build_rigs=True, high_res=True):
    """Add a single part and return the builder's own Part wrapper.
    high_res=False always places the builder's fbx proxy."""
    # model_id picks the mesh, object_id is what the part is; they differ only
    # for alternate forms - see dictionary.export_object_id
    model_id = object_id.replace("^", "")
    object_id = dictionary.export_object_id(model_id)

    # read before the part exists, as making it changes the selection
    matrix = new_part_matrix()

    # parts with a class of their own are always built by it, then upgraded
    override_class = get_override_class(builder_object, object_id)
    if override_class is not None:
        item = override_class(
            object_id=object_id,
            builder_object=builder_object,
            user_data=user_data,
            build_rigs=build_rigs,
        )
        if high_res:
            upgrade_to_high_res(item.object)
        item.object.matrix_world = matrix
        return item

    # ids the library doesn't cover fall back to the proxy, moved to `matrix`
    # afterwards since the builder always places it on the active object
    bpy_object = new_high_res_object(model_id) if high_res else None
    if bpy_object is None:
        item = _add_proxy_part(builder_object, object_id, user_data, build_rigs)
        if item is not None and getattr(item, "object", None) is not None:
            item.object.matrix_world = matrix
        return item

    part_class = get_default_part_class(builder_object)
    stamp_part_properties(bpy_object, object_id, part_class)
    if model_id != object_id:
        # which model this placement shows; never exported
        bpy_object["nms_form_model"] = model_id

    # colour by object property so the mesh stays shared; a new part gets the
    # game's default palette for it
    if user_data is None:
        user_data = materials.default_user_data(object_id)
    materials.recolour_from_user_data([bpy_object], user_data)

    # collapse textures and node groups a fresh append duplicated; cheap if
    # there's nothing to do
    materials.dedupe_appended_data()
    materials.prepare_materials(bpy_object.data.materials)

    item = part_class(
        bpy_object=bpy_object, builder_object=builder_object, build_rigs=build_rigs
    )
    item.reset_transforms()
    item.object.matrix_world = matrix

    return item


def new_merge_source(object_id, user_data, high_res=True, proxy_cache=None, catalog=None):
    """A bare part object about to be merged into a group, with only ObjectID and
    UserData set. Falls back to the other library; None if neither has the id."""
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
