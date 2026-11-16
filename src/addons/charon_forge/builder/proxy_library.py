"""The fbx proxy library: one cached base mesh per id, copied per UserData
because a proxy's colour is a flat material."""

import os

import bpy

from ..objects.part import Part
from ..utils import mesh_utils, variant_map
from .. import materials
from ..utils.base_builder_utils import blend_utils
from . import asset_library

PROXY_MESH_PREFIX = "NMS_LR_"
PROXY_MESH_TAG = "nms_proxy_id"

# Tags each (ObjectID, UserData) copy so later passes reuse it instead of
# making a fresh copy every time the scene switches back to proxies.
PROXY_PLACEMENT_TAG = "nms_proxy_placement"

# Properties painting a proxy writes; copied straight onto later placements
# of the same (ObjectID, UserData) instead of painting again.
PROXY_CARRIED_PROPS = (
    Part.PROP_USER_DATA,
    materials.PROP_READONLY_COLOUR,
    materials.PROP_READONLY_MATERIAL,
)


def _resolve_catalog(catalog):
    if catalog is not None:
        return catalog
    # imported on use - the package imports this module
    from . import get_builder
    return get_builder()


def load_proxy_mesh(object_id, catalog=None):
    """The uncoloured fbx proxy mesh for an id, imported on first use.
    None when the id has no fbx."""
    mesh_name = PROXY_MESH_PREFIX + object_id
    cached = bpy.data.meshes.get(mesh_name)
    if cached is not None and cached.get(PROXY_MESH_TAG) == object_id:
        return cached

    # same variant rebuild as the high res side, under the same (off) switch -
    # see asset_library.REBUILD_VARIANTS
    if asset_library.REBUILD_VARIANTS:
        mesh = rebuild_variant_proxy_mesh(object_id, catalog)
        if mesh is not None:
            return mesh

    fbx_path = _resolve_catalog(catalog).get_obj_path(object_id)
    if not fbx_path or not os.path.isfile(fbx_path):
        return None

    # every object the import brought in, so extras like armatures or empties
    # don't stay behind in the scene
    objects_before = set(bpy.data.objects)
    try:
        mesh_utils.import_model(fbx_path)
    except RuntimeError:
        return None
    imported = [item for item in bpy.data.objects if item not in objects_before]

    mesh = None
    for item in imported:
        if mesh is None and item.type == "MESH":
            mesh = item.data
            mesh.materials.clear()
        bpy.data.objects.remove(item, do_unlink=True)

    if mesh is None:
        return None

    mesh.name = mesh_name
    mesh[PROXY_MESH_TAG] = object_id
    return mesh


def rebuild_variant_proxy_mesh(object_id, catalog=None):
    """Build a variant's fbx proxy by transforming its root's proxy, or None.
    The proxy twin of asset_library.rebuild_variant_mesh."""
    rebuild = variant_map.get_rebuild(object_id)
    if rebuild is None:
        return None

    root_id, matrix = rebuild
    if root_id == object_id:
        return None

    root_mesh = load_proxy_mesh(root_id, catalog)
    if root_mesh is None:
        return None

    mesh = asset_library.transformed_copy(root_mesh, matrix)
    mesh.name = PROXY_MESH_PREFIX + object_id
    mesh[PROXY_MESH_TAG] = object_id
    return mesh


def _find_proxy_placement_mesh(key):
    """The proxy mesh already made for one (ObjectID, UserData), if any.
    Matched on the tag, so a user's mesh with the same name is never picked."""
    mesh = bpy.data.meshes.get("%s_%s" % key)
    if mesh is not None and mesh.get(PROXY_PLACEMENT_TAG) == "%s/%s" % key:
        return mesh
    return None


def apply_proxy_mesh(bpy_object, object_id, user_data, cache=None, catalog=None):
    """Point an object at the fbx proxy mesh for one (id, UserData), touching only
    mesh and colour. False (object unchanged) when the id has no fbx."""
    if user_data is None:
        user_data = Part.DEFAULT_USER_DATA
    key = (object_id, str(user_data))
    entry = cache.get(key) if cache is not None else None

    if entry is not None:
        mesh, carried, colour = entry
        bpy_object.data = mesh
        # drop the high res palette properties, which mean nothing to a proxy
        materials.clear(bpy_object)
        for name, value in carried.items():
            bpy_object[name] = value
        bpy_object.color = colour
        return True

    mesh = _find_proxy_placement_mesh(key)
    if mesh is None:
        base_mesh = load_proxy_mesh(object_id, catalog)
        if base_mesh is None:
            return False

        # a private copy per pair, because painting it writes into its slot 0
        mesh = base_mesh.copy()
        mesh.name = "%s_%s" % key
        # the copy must not answer to load_proxy_mesh's tag
        if PROXY_MESH_TAG in mesh:
            del mesh[PROXY_MESH_TAG]
        mesh[PROXY_PLACEMENT_TAG] = "%s/%s" % key

    bpy_object.data = mesh
    materials.clear(bpy_object)
    # paints slot 0 of the copy, and writes UserData and the readable labels
    materials.restore_material(bpy_object, key[1])

    if cache is not None:
        cache[key] = (
            mesh,
            {
                name: bpy_object[name]
                for name in PROXY_CARRIED_PROPS
                if name in bpy_object
            },
            tuple(bpy_object.color),
        )

    return True


def new_proxy_object(object_id, user_data, cache=None, catalog=None):
    """A bare object over an fbx proxy mesh, coloured for one UserData.
    None when the id has no fbx; part properties are the caller's job."""
    # created over the base mesh, as an object made with no data is an Empty
    base_mesh = load_proxy_mesh(object_id, catalog)
    if base_mesh is None:
        return None

    bpy_object = bpy.data.objects.new(object_id, base_mesh)
    blend_utils.add_to_scene(bpy_object)
    apply_proxy_mesh(bpy_object, object_id, user_data, cache=cache, catalog=catalog)
    return bpy_object
