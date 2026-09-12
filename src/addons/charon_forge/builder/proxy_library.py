"""The old fbx proxy library, cached the way the high res meshes are.

One base mesh per object id, imported once and kept in bpy.data under
PROXY_MESH_PREFIX so a second pass over the same id in the same session never
touches the disk.

Unlike a high res mesh this one cannot be shared by the parts that use it: a
proxy's colour is a flat material in slot 0, so a placement needs its own copy
of the mesh per UserData. What the cache saves is the fbx import itself, which
is by far the expensive half.

Every function takes the `catalog` to find fbx files through - anything with
get_obj_path(), which every builder has. Left out, the default Charon builder
is used.
"""

import os

import bpy

from ..objects.part import Part
from ..utils import variant_map
from .. import materials
from ..utils.base_builder_utils import blend_utils
from . import asset_library

PROXY_MESH_PREFIX = "NMS_LR_"
PROXY_MESH_TAG = "nms_proxy_id"

# Written onto each per (ObjectID, UserData) copy taken off a base mesh, so a
# later pass can find the one it made last time instead of taking another. A
# scene switched back to high res leaves all of these with no users, and
# without this every switch back down would copy a whole fresh set.
PROXY_PLACEMENT_TAG = "nms_proxy_placement"

# The custom properties utils.materials.assign_material writes onto an object
# when it paints a proxy. They belong to the (ObjectID, UserData) pair rather
# than to the placement, so a second placement of the same pair can be given
# them wholesale instead of running the whole paint again.
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
    """Get the uncoloured fbx proxy mesh for an id, importing it on first use.

    The mesh comes back with no materials on it - the caller is expected to
    copy it per UserData and let utils.materials.restore_material paint the copy.

    Returns:
        bpy.types.Mesh: The base mesh, or None when there is no fbx for the
            id, in which case the caller should leave whatever it has alone
            rather than substituting anything.
    """
    mesh_name = PROXY_MESH_PREFIX + object_id
    cached = bpy.data.meshes.get(mesh_name)
    if cached is not None and cached.get(PROXY_MESH_TAG) == object_id:
        return cached

    # Same rebuild the high res side does, and for the same reason - the fbx
    # library has the wrong mesh under a lot of the corvette variant ids. The
    # proxies are stored in the same space as the high res assets, so the
    # transform out of objects_map.json applies to them unchanged.
    if asset_library.REBUILD_VARIANTS:
        mesh = rebuild_variant_proxy_mesh(object_id, catalog)
        if mesh is not None:
            return mesh

    fbx_path = _resolve_catalog(catalog).get_obj_path(object_id)
    if not fbx_path or not os.path.isfile(fbx_path):
        return None

    # Every new object the import brought in, not just the one it happened to
    # hand back: an fbx that carries an armature or an empty alongside its mesh
    # would otherwise leave the extras behind in the scene.
    objects_before = set(bpy.data.objects)
    try:
        bpy.ops.import_scene.fbx(filepath=fbx_path)
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
    """Build a variant's fbx proxy by transforming its root part's proxy.

    The proxy twin of asset_library.rebuild_variant_mesh - same table, same
    transform, only the cache it lands in differs.

    Returns:
        bpy.types.Mesh: The rebuilt base mesh, or None when the id is not a
            reproducible variant or there is no fbx for its root.
    """
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
    """The proxy mesh already cut for one (ObjectID, UserData), if there is one.

    Matched on the tag rather than on the name alone, so a mesh of the user's
    own that happens to be called CUBEROOM_1 is never mistaken for one of ours.
    """
    mesh = bpy.data.meshes.get("%s_%s" % key)
    if mesh is not None and mesh.get(PROXY_PLACEMENT_TAG) == "%s/%s" % key:
        return mesh
    return None


def apply_proxy_mesh(bpy_object, object_id, user_data, cache=None, catalog=None):
    """Point an existing object at the fbx proxy mesh for one (id, UserData).

    Nothing but the mesh and the colour is touched, so this is also the whole
    of what it takes to turn a placed high res part back into a proxy.

    Args:
        bpy_object (bpy.types.Object): The object to point at the proxy.
        object_id (str): The part it is a placement of.
        user_data: The packed UserData value for this placement.
        cache (dict): Optional {(object id, UserData): (mesh, properties,
            colour)} carried across a batch of placements, so the paint is
            paid for once per pair rather than once per placement.
        catalog: Where to find the fbx files.

    Returns:
        bool: False when there is no fbx for the id, in which case the object
            is left exactly as it was.
    """
    if user_data is None:
        user_data = Part.DEFAULT_USER_DATA
    key = (object_id, str(user_data))
    entry = cache.get(key) if cache is not None else None

    if entry is not None:
        mesh, carried, colour = entry
        bpy_object.data = mesh
        # the palette properties drive the high res colourise node group and
        # mean nothing to a flat material, so an object that keeps them reads
        # as half converted to anything that inspects it afterwards
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
        # the copy is a placement mesh, not the cached import it came from -
        # it must not answer to load_proxy_mesh's tag
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
    """Make a bare object over an fbx proxy mesh, coloured for one UserData.

    No part properties are set beyond the ones painting writes - that is the
    caller's job, the same as for placement.new_high_res_object.

    Returns:
        bpy.types.Object: The new object, or None when there is no fbx for the
            id, so the caller can decide what to do about it.
    """
    # The object has to be born over some mesh before it can be pointed at the
    # right one - an object made with no data is an Empty, and an Empty cannot
    # be given a mesh afterwards. load_proxy_mesh is cached, so asking for the
    # base here and again inside apply_proxy_mesh costs one dict lookup.
    base_mesh = load_proxy_mesh(object_id, catalog)
    if base_mesh is None:
        return None

    bpy_object = bpy.data.objects.new(object_id, base_mesh)
    blend_utils.add_to_scene(bpy_object)
    apply_proxy_mesh(bpy_object, object_id, user_data, cache=cache, catalog=catalog)
    return bpy_object
