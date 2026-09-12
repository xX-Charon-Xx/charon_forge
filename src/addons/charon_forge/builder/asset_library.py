"""The high resolution asset library - which .blend holds which part, and
getting its mesh into bpy.data.

Nothing here makes objects or knows about builders; it only hands out mesh
datablocks. See placement.py for turning those into parts.
"""

import os

import bpy

from .. import materials
from ..nms.utils import blend_utils, variant_map
from . import paths

# An earlier build of the library shipped some ids as several style variants,
# named <ID>__<STYLE>.blend, because two styles cannot live in one file without
# breaking the one-object-per-file rule. The current library is flat - one file
# per id, no suffixes - so nothing hits this any more, but it is kept so a
# styled file dropped into the folder still resolves instead of being ignored.
# Order of preference, chosen by matching each variant's bounding box against
# the fbx proxy: Builders won 16 of the 17 pairs tested, Exterior all 3 corvette
# cockpits. An id whose styles are all outside this list is left out of the
# index on purpose and falls back to the fbx proxy - that was the FRE_ROOM_*
# room kits, where no single piece is the room and picking one would be wrong.
STYLE_PRIORITY = ("Builders", "Exterior")

# Appended meshes are cached in bpy.data under this prefix so a second import in
# the same session (or after a reload) reuses them instead of touching the disk.
# The tag written alongside it is what marks a part as belonging to the new
# colour system - it lives in materials/properties.py so the flat material code
# can read it without importing the builder.
MESH_PREFIX = "NMS_HR_"
MESH_TAG = materials.MESH_TAG

# False places every id from its own asset again, the way the addon did before
# the variant map existed. Kept as a switch because it is the one thing to turn
# off if a rebuilt part ever looks worse than the asset it replaced.
REBUILD_VARIANTS = True

# Strip the doubled geometry a lot of the library ships with as each asset is
# appended - see blend_utils.remove_duplicate_faces for what it is and why it
# only shows up in Cycles. Done here rather than in the asset files because the
# library is generated: fixing the blends by hand would last until the next
# extraction run, and this also covers whatever is generated next. Runs once
# per part per session, on the shared mesh every placement then points at.
CLEAN_DUPLICATE_FACES = True

# Set once per session by get_asset_index().
_asset_index = None


def get_asset_index(rebuild=False):
    """The {object_id: blend file} lookup for the library, built once."""
    global _asset_index

    if _asset_index is not None and not rebuild:
        return _asset_index

    _asset_index = {}
    if not os.path.isdir(paths.HIGH_RES_PATH):
        return _asset_index

    # collect every candidate first, then resolve the styled ones, so the
    # answer doesn't depend on the order the folder happens to list in
    candidates = {}
    for filename in os.listdir(paths.HIGH_RES_PATH):
        if not filename.endswith(".blend"):
            continue
        object_id, separator, style = filename[:-6].partition("__")
        candidates.setdefault(object_id, []).append(
            (style if separator else None, os.path.join(paths.HIGH_RES_PATH, filename))
        )

    for object_id, styles in candidates.items():
        if len(styles) == 1 and styles[0][0] is None:
            _asset_index[object_id] = styles[0][1]
            continue

        # a multi style id is only usable if one of its styles is one we chose
        for preferred in STYLE_PRIORITY:
            for style, path in styles:
                if style == preferred:
                    _asset_index[object_id] = path
                    break
            if object_id in _asset_index:
                break

    return _asset_index


def has_asset(object_id):
    """True when the library has a .blend of its own for this id."""
    return object_id.replace("^", "") in get_asset_index()


def load_high_res_mesh(object_id, asset_index=None):
    """The shared mesh datablock for an object id, appending it on first use.

    Returns:
        bpy.types.Mesh: The mesh, or None when the library doesn't cover the id.
    """
    asset_index = asset_index if asset_index is not None else get_asset_index()

    # the cache lives in bpy.data rather than in a module level dict, so it
    # survives a new file, a module reload and a scene the user already saved
    mesh_name = MESH_PREFIX + object_id
    cached = bpy.data.meshes.get(mesh_name)
    if cached is not None and cached.get(MESH_TAG) == object_id:
        return cached

    # A reproducible variant is built out of the mesh it is a variant of rather
    # than out of its own asset - most of the corvette variants ship the wrong
    # mesh, and the transform in objects_map.json is measured, so this is the
    # more trustworthy of the two. See nms/utils/variant_map.py.
    if REBUILD_VARIANTS:
        mesh = rebuild_variant_mesh(object_id, asset_index)
        if mesh is not None:
            return mesh

    blend_path = asset_index.get(object_id)
    if blend_path is None:
        return None

    # every library file holds exactly one mesh object. We only want its mesh -
    # the object datablock is thrown away and each placement gets a fresh one
    with bpy.data.libraries.load(blend_path, link=False) as (source, target):
        target.objects = list(source.objects)

    mesh = None
    for appended_object in target.objects:
        if appended_object is None:
            continue
        if mesh is None and appended_object.type == "MESH":
            mesh = appended_object.data
        bpy.data.objects.remove(appended_object)

    if mesh is None:
        return None

    mesh.name = mesh_name
    mesh[MESH_TAG] = object_id
    if CLEAN_DUPLICATE_FACES:
        blend_utils.remove_duplicate_faces(mesh)
    # The append brought this asset's own copies of its textures and of the
    # colourise node group with it. A caller inside a deferred block is not
    # going to call the collapse itself, so tell it there is now something to
    # collapse - see materials.note_appended_data.
    materials.note_appended_data()
    return mesh


def rebuild_variant_mesh(object_id, asset_index=None):
    """Build a variant's mesh by transforming the mesh of its root part.

    Only reproducible variants come back with anything - for everything else
    this returns None and the caller loads the id's own asset as usual. The
    result is cached and tagged exactly like an appended mesh, so from here on
    it is shared across placements and picked up by the cache in
    load_high_res_mesh like any other.

    Returns:
        bpy.types.Mesh: The rebuilt mesh, or None when the id is not a
            reproducible variant or its root has no asset to build from.
    """
    rebuild = variant_map.get_rebuild(object_id)
    if rebuild is None:
        return None

    root_id, matrix = rebuild
    # guards a map that ever names an id as its own root - the recursion below
    # would otherwise never reach an asset
    if root_id == object_id:
        return None

    root_mesh = load_high_res_mesh(root_id, asset_index)
    if root_mesh is None:
        return None

    # Materials come across with the copy as references, so the variant paints
    # from the root's and the palette properties still work.
    mesh = transformed_copy(root_mesh, matrix)
    mesh.name = MESH_PREFIX + object_id
    mesh[MESH_TAG] = object_id
    return mesh


def transformed_copy(mesh, matrix):
    """A copy of a mesh with a mesh space matrix baked into it.

    Always a copy - the mesh being read here is the shared datablock every
    placement of the root part is pointing at, and transforming that in place
    would move every one of them.

    Returns:
        bpy.types.Mesh: The new mesh. Unnamed and untagged - the caller owns
            both, because the two libraries name their caches differently.
    """
    copied = mesh.copy()
    copied.transform(matrix)

    # a mirrored transform turns the mesh inside out
    if matrix.to_3x3().determinant() < 0.0:
        copied.flip_normals()

    return copied
