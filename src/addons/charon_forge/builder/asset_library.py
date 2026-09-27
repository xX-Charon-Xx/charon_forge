"""The high resolution asset library - which .blend holds which part, and
getting its mesh into bpy.data.

Nothing here makes objects or knows about builders; it only hands out mesh
datablocks. See placement.py for turning those into parts.
"""

import os
import time

import bmesh
import bpy
import numpy as np

from .. import materials
from ..utils import loading_overlay, variant_map
from ..utils.base_builder_utils import blend_utils
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
# appended - see _remove_duplicate_faces below for what it is and why it only
# shows up in Cycles. The extraction pipeline now does this when it builds an
# asset and tags the mesh (CLEAN_TAG), so this only runs for assets without
# the tag - a library built before that. Runs once per part per session, on
# the shared mesh every placement then points at.
CLEAN_DUPLICATE_FACES = True

# Two faces count as facing the same way when their normals agree at least
# this closely. Well above anything a rounding difference produces, and well
# below the angle a genuine back face sits at.
FACING_TOLERANCE = 0.9

# On a library mesh: the pipeline already removed its duplicate faces
# (pipeline/blend/dupfaces.py), so appending it skips the clean below. A mesh
# without it - an older library - is still cleaned here.
CLEAN_TAG = "nms_faces_clean"

# Set once per session by get_asset_index().
_asset_index = None

# Seconds spent in each stage of loading assets, and how many were loaded,
# since the last reset_load_stats() - the importer prints them after a build
# so a slow import shows where its time went.
_load_stats = {"assets": 0, "append": 0.0, "merge": 0.0, "clean": 0.0, "glow": 0.0}


def reset_load_stats():
    for key in _load_stats:
        _load_stats[key] = 0 if key == "assets" else 0.0


def get_load_stats():
    return dict(_load_stats)


def _find_duplicate_faces(coords, normals, loop_starts, loop_totals, loop_vertices, precision=5):
    """The faces that sit exactly on top of an earlier face pointing the same way.

    Pure numpy over flat arrays, so it can be checked without Blender - see
    _remove_duplicate_faces for what the duplicates are and why they go.

    A face's key is the sorted set of its vertices' positions, rounded to
    `precision` decimals the way int() truncates. Faces sharing a key are
    compared in index order: each one is dropped if it faces the same way as
    one already kept, and kept otherwise (a genuine back face).

    Args:
        coords: vertex positions, flat (x, y, z, x, y, z, ...).
        normals: face normals, flat.
        loop_starts, loop_totals: per face, its first loop and loop count.
        loop_vertices: per loop, its vertex index.

    Returns:
        list: Indices of the faces to remove, ascending.
    """
    face_count = len(loop_totals)
    if face_count < 2:
        return []

    # one id per distinct rounded position, so faces made of separate but
    # coincident vertices still share a key
    scale = 10 ** precision
    positions = np.trunc(np.asarray(coords, dtype=np.float64).reshape(-1, 3) * scale).astype(np.int64)
    # each row viewed as one 24 byte value: a 1-D unique, about twice as
    # fast as np.unique(axis=0) on the same rows
    packed = np.ascontiguousarray(positions).view(np.dtype((np.void, 24))).reshape(-1)
    _, position_ids = np.unique(packed, return_inverse=True)
    loop_positions = position_ids.reshape(-1)[np.asarray(loop_vertices, dtype=np.int64)]

    starts = np.asarray(loop_starts, dtype=np.int64)
    totals = np.asarray(loop_totals, dtype=np.int64)
    normals = np.asarray(normals, dtype=np.float64).reshape(-1, 3)

    doomed = []
    # faces can only match faces with the same number of corners, so each
    # corner count is its own fixed width table
    for corners in np.unique(totals):
        faces = np.nonzero(totals == corners)[0]
        if len(faces) < 2:
            continue

        keys = np.sort(loop_positions[starts[faces, None] + np.arange(corners)], axis=1)

        # sort the keys so equal ones sit next to each other; the face index
        # as the last tiebreak keeps each run in index order
        order = np.lexsort((faces,) + tuple(keys[:, column] for column in range(corners - 1, -1, -1)))
        sorted_keys = keys[order]
        same_as_previous = np.all(sorted_keys[1:] == sorted_keys[:-1], axis=1)
        if not same_as_previous.any():
            continue

        run_starts = np.nonzero(np.concatenate(([True], ~same_as_previous)))[0]
        run_lengths = np.diff(np.append(run_starts, len(order)))

        # nearly every duplicate is one pair - those are settled in one go:
        # the second of the two goes when it faces the same way as the first
        pair_starts = run_starts[run_lengths == 2]
        firsts = faces[order[pair_starts]]
        seconds = faces[order[pair_starts + 1]]
        facing = np.einsum("ij,ij->i", normals[seconds], normals[firsts])
        doomed.extend(seconds[facing > FACING_TOLERANCE].tolist())

        # three or more faces on one key, one at a time
        for start, length in zip(run_starts, run_lengths):
            if length < 3:
                continue
            end = start + length
            kept = []
            for face in faces[order[start:end]]:
                normal = normals[face]
                if any(float(normal @ normals[other]) > FACING_TOLERANCE for other in kept):
                    doomed.append(int(face))
                else:
                    # the first of its key, or coincident but pointing
                    # elsewhere - a real back face, kept
                    kept.append(face)

    doomed.sort()
    return doomed


def _remove_duplicate_faces(mesh, precision=5):
    """Drop faces that sit exactly on top of another face pointing the same way.

    A lot of the models-high-res library was built by joining two source meshes
    without merging where they overlapped - T_WALL_Q_H1 ships 76 such pairs,
    B_WNG_B nearly 20,000. Two faces at the same depth are a coin flip for a ray
    tracer, and because the duplicates carry their own custom split normals the
    losing pick shades black: the part renders with black patches in Cycles
    while the viewport and EEVEE, whose rasteriser breaks the tie consistently,
    look perfectly fine.

    Only exact duplicates go: the same set of vertex positions AND facing the
    same way. Faces that coincide but point in opposite directions are how
    decals, holograms, foliage and glass are modelled all through the library -
    BLD_PLANET_HOLO is 16,848 of them against 96 real duplicates - and those
    have to survive untouched.

    Positions rather than vertex indices, because the joined halves bring their
    own vertices: the duplicated faces in T_WALL_Q_H1 sit on 820 coincident but
    separate vertices, so nothing about the indices gives the overlap away.

    The search is numpy (_find_duplicate_faces): it runs over every face of
    every mesh appended, a few hundred thousand on the big corvette parts,
    which in plain python was most of the time it took to place one.

    This is specific to how models-high-res was generated, so unlike
    add_to_scene/select/and so on it has no equivalent in the base builder
    addon and stays implemented here rather than resolved through it.

    Args:
        mesh (bpy.types.Mesh): The mesh to clean, edited in place.
        precision (int): Decimal places a position is compared at.

    Returns:
        int: How many faces were removed.
    """
    face_count = len(mesh.polygons)
    if face_count < 2:
        return 0

    # foreach_get straight into numpy buffers of the property's own type -
    # no per element access and no conversion on the way out
    coords = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", coords)
    normals = np.empty(face_count * 3, dtype=np.float32)
    mesh.polygons.foreach_get("normal", normals)
    loop_starts = np.empty(face_count, dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", loop_starts)
    loop_totals = np.empty(face_count, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", loop_totals)
    loop_vertices = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_vertices)

    doomed = _find_duplicate_faces(
        coords, normals, loop_starts, loop_totals, loop_vertices, precision
    )
    if not doomed:
        return 0

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    # 'FACES' takes the vertices and edges left behind with them, so the
    # duplicated halves stop costing memory as well as rendering wrong
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in doomed], context='FACES')
    bm.to_mesh(mesh)
    bm.free()

    return len(doomed)


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


def _cached_mesh(object_id):
    """The id's mesh when this file already has it, else None."""
    # the cache lives in bpy.data rather than in a module level dict, so it
    # survives a new file, a module reload and a scene the user already saved
    cached = bpy.data.meshes.get(MESH_PREFIX + object_id)
    if cached is not None and cached.get(MESH_TAG) == object_id:
        return cached
    return None


def load_high_res_mesh(object_id, asset_index=None, _leftovers=None):
    """The shared mesh datablock for an object id, appending it on first use.

    Returns:
        bpy.types.Mesh: The mesh, or None when the library doesn't cover the id.
    """
    asset_index = asset_index if asset_index is not None else get_asset_index()

    cached = _cached_mesh(object_id)
    if cached is not None:
        return cached

    # A reproducible variant is built out of the mesh it is a variant of rather
    # than out of its own asset - most of the corvette variants ship the wrong
    # mesh, and the transform in objects_map.json is measured, so this is the
    # more trustworthy of the two. See nms/utils/variant_map.py.
    if REBUILD_VARIANTS:
        mesh = rebuild_variant_mesh(object_id, asset_index, _leftovers)
        if mesh is not None:
            return mesh

    blend_path = asset_index.get(object_id)
    if blend_path is None:
        return None

    if _leftovers is not None:
        return _append_asset(object_id, blend_path, _leftovers)
    leftovers = []
    mesh = _append_asset(object_id, blend_path, leftovers)
    if leftovers:
        bpy.data.batch_remove(leftovers)
    return mesh


def load_high_res_meshes(object_ids, asset_index=None):
    """The shared mesh of every id at once - what a bulk import asks for.

    Every asset the ids need is appended in one go before anything is built,
    variants' roots first, and whatever the appends leave over (the asset
    files' own objects) is removed in a single batch_remove at the end rather
    than one rescan of the file per asset.

    Returns:
        dict: {object_id: mesh, or None when the library doesn't cover it}
    """
    asset_index = asset_index if asset_index is not None else get_asset_index()
    leftovers = []
    meshes = {}
    unique_ids = list(dict.fromkeys(object_ids))
    for index, object_id in enumerate(unique_ids):
        loading_overlay.step("Loading assets", index / len(unique_ids))
        meshes[object_id] = load_high_res_mesh(object_id, asset_index, leftovers)
    if leftovers:
        bpy.data.batch_remove(leftovers)
    return meshes


def _append_asset(object_id, blend_path, leftovers):
    """Append an id's asset and make its mesh the id's shared mesh.

    Only the mesh is wanted: each placement gets a fresh object. An asset
    holding the one mesh has just that appended; any other shape of file has
    its objects appended, the first mesh object's mesh kept, and the objects
    added to `leftovers` for the caller to remove in one batch.
    """
    started = time.perf_counter()
    with bpy.data.libraries.load(blend_path, link=False) as (source, target):
        if len(source.meshes) == 1:
            target.meshes = list(source.meshes)
        else:
            target.objects = list(source.objects)

    mesh = None
    if target.meshes:
        mesh = target.meshes[0]
    for appended_object in target.objects:
        if appended_object is None:
            continue
        if mesh is None and appended_object.type == "MESH":
            mesh = appended_object.data
        leftovers.append(appended_object)

    appended = time.perf_counter()
    _load_stats["append"] += appended - started
    if mesh is None:
        return None

    _load_stats["assets"] += 1
    mesh.name = MESH_PREFIX + object_id
    mesh[MESH_TAG] = object_id
    # the asset's copies of materials the file already has go straight away,
    # so the next append doesn't pay for them - see materials/merge.py
    materials.merge.merge_appended(mesh)
    merged = time.perf_counter()
    _load_stats["merge"] += merged - appended
    if CLEAN_DUPLICATE_FACES and not mesh.get(CLEAN_TAG):
        _remove_duplicate_faces(mesh)
    cleaned = time.perf_counter()
    _load_stats["clean"] += cleaned - merged
    # a lamp's glow carries the power of the part's game lights - see
    # materials/emission.py
    materials.emission.stamp_glow(mesh, object_id)
    _load_stats["glow"] += time.perf_counter() - cleaned
    # The append brought this asset's own copies of its textures and of the
    # colourise node group with it. A caller inside a deferred block is not
    # going to call the collapse itself, so tell it there is now something to
    # collapse - see materials.note_appended_data.
    materials.note_appended_data()
    return mesh


def rebuild_variant_mesh(object_id, asset_index=None, _leftovers=None):
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

    root_mesh = load_high_res_mesh(root_id, asset_index, _leftovers)
    if root_mesh is None:
        return None

    # Materials come across with the copy as references, so the variant paints
    # from the root's and the palette properties still work.
    mesh = transformed_copy(root_mesh, matrix)
    mesh.name = MESH_PREFIX + object_id
    mesh[MESH_TAG] = object_id
    materials.emission.stamp_glow(mesh, object_id)
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


def reimport_library_meshes():
    """Append every library part in the file again from its asset, as it is
    on disk now, and move everything that used the old mesh onto the new one
    - placed parts, and the part copies the Forge's objects hold. What the
    old version brought in (its materials, textures, node groups) is removed
    once nothing uses it.

    Groups are merged meshes of their own and are rebuilt separately - see
    Group.switch_scene_proxy_quality(force=True).

    Returns:
        (int, int): parts reimported, and parts whose asset could not be
            loaded (left as they were).
    """
    old_meshes = [mesh for mesh in bpy.data.meshes
                  if MESH_TAG in mesh and mesh.library is None
                  and mesh.name.startswith(MESH_PREFIX)]
    if not old_meshes:
        return 0, 0

    # the asset files may have been added, moved or renamed since the index
    # was read
    get_asset_index(rebuild=True)
    old_materials = {mat for mesh in old_meshes for mat in mesh.materials if mat}

    # out of the cache - renamed, load_high_res_mesh no longer finds them and
    # appends each part afresh (a variant rebuilds from its freshly loaded root)
    for mesh in old_meshes:
        mesh.name = "OLD_" + mesh.name

    reimported = failed = 0
    retired = []
    with materials.defer_shared_data():
        object_ids = [mesh[MESH_TAG] for mesh in old_meshes]
        try:
            new_meshes = load_high_res_meshes(object_ids)
        except Exception as error:                         # noqa: BLE001
            # one bad asset spoils the batch - fall back to each on its own,
            # so only the bad one is left as it was
            print("Charon Forge: batch reimport failed, one at a time: %r" % (error,))
            new_meshes = {}
            for object_id in object_ids:
                try:
                    new_meshes[object_id] = load_high_res_mesh(object_id)
                except Exception as error:                 # noqa: BLE001
                    print("Charon Forge: could not reimport %s: %r" % (object_id, error))
        for mesh, object_id in zip(old_meshes, object_ids):
            new_mesh = new_meshes.get(object_id)
            if new_mesh is None or new_mesh == mesh:
                # keep the old one - and put its name back so it's found again
                mesh.name = MESH_PREFIX + object_id
                failed += 1
                continue
            mesh.user_remap(new_mesh)
            retired.append(mesh)
            reimported += 1

    bpy.data.batch_remove([mesh for mesh in retired if mesh.users == 0])
    _remove_unused(old_materials)
    return reimported, failed


def _remove_unused(old_materials):
    """Remove old materials nothing uses now, then the textures and node
    groups only they used - again until nothing more comes free."""
    candidates = set()
    for mat in old_materials:
        if mat.node_tree is not None:
            candidates |= _tree_blocks(mat.node_tree)
    unused = [mat for mat in old_materials if mat.users == 0]
    while unused:
        bpy.data.batch_remove(unused)
        unused = [block for block in list(candidates)
                  if _alive(block) and block.users == 0]
        candidates = {block for block in candidates if _alive(block) and block not in unused}


def _tree_blocks(tree, seen=None):
    """The images and node groups a node tree uses, nested groups included."""
    seen = set() if seen is None else seen
    for node in tree.nodes:
        image = getattr(node, "image", None)
        if image is not None:
            seen.add(image)
        group = getattr(node, "node_tree", None)
        if group is not None and group not in seen:
            seen.add(group)
            _tree_blocks(group, seen)
    return seen


def _alive(block):
    try:
        block.name
        return True
    except ReferenceError:
        return False
