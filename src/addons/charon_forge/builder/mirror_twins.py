"""Placing a part's mirror or flip twin from the high res library.

The base builder addon mirrors a part by swapping it for its twin id (B_STR_B_N
-> B_STR_B_S) and scaling a copy of the current mesh by -1 on the part's local
X (Y for a flip), then works out the twin's matrix on the understanding that
the twin IS that flipped mesh. For a lot of pairs it is not. The game's
B_STR_B_S is B_STR_B_N flipped on Z - the fbx proxies say so too - which is the
flip on X turned 180 degrees about the part's up axis. Exported at the
addon's matrix, the twin comes out in game pointing the other way; the old
proxies hid that, since they show the flipped copy rather than the twin.

High res parts are swapped for the twin's own library mesh instead (see
HighResBuilderMixin._swap_to_high_res_twin), so they show what the game shows.
resources/objects_map.json records how every variant's mesh is made from its
root's, so the difference between "the current mesh flipped" and "the twin's
mesh" is known exactly:

    twin mesh     = R @ current mesh          R from objects_map.json
    wanted in world = M @ F @ current mesh    M the addon's matrix, F the flip
    so the twin goes at  M @ C,  C = F @ R^-1

C is a rotation whenever the twin really is a mirror image. Only its rotation
is used: offsets between a part and its twin are how the game keeps the twin
in the part's slot, and moving the twin by them would take it out again.

When the twin is a rotation of the part instead (B_STR_AA_S is B_STR_AA_N
turned round, and so is B_DECO_Q_1 of B_DECO_Q_0) C is a reflection, and no
placement can show a true mirror image - the game has none of that part. What
it can show is the placement that comes closest, and that depends on the
part's own shape: any symmetry G of the current mesh (G @ mesh looks like the
mesh) gives another way of writing what is wanted,

    M @ F @ current mesh  ~  M @ F @ G @ current mesh,  C = F @ G @ R^-1

so the candidates are checked against the mesh (see _symmetry_score) and the
best match whose C is a rotation is used. For B_STR_AA_N that is its near
left/right symmetry: the twin is turned back round and sits exactly where the
old proxies showed the mirrored part, with only its asymmetric details
differing - which is what the game will show too. G is the identity, and C
exact, for a twin that is a true mirror image.

Flipping needs none of this. The addon's flip keeps the part's matrix and only
swaps the id, and the game's flipped model (B_STR_B_Y_N) is built to sit in
the same slot - what the library shows is already what the game shows.

The addon sets the twin's matrix after mirror_part returns, so the correction
is noted at the swap and applied when its mirror tool finishes - see
host_patches.py. Mirrored group caches are corrected directly.
"""

import json

import mathutils
import numpy as np

from ..utils import variant_map
from . import asset_library

MIRROR = "MIRROR"
FLIP = "FLIP"

# the flip the addon applies to the mesh when mirroring, in mesh space
_MIRROR_FLIP = (-1.0, 1.0, 1.0)

# corrections closer than this to the identity are not worth applying
TOLERANCE = 1e-4

# The symmetries a part might have, tried in this order - a tie goes to the
# earlier one, so an exact correction (the identity) always wins.
_SYMMETRIES = (
    ("identity", (1.0, 1.0, 1.0)),
    ("flip x", (-1.0, 1.0, 1.0)),
    ("flip z", (1.0, 1.0, -1.0)),
    ("flip y", (1.0, -1.0, 1.0)),
    ("turn y", (-1.0, 1.0, -1.0)),
    ("turn z", (-1.0, -1.0, 1.0)),
    ("turn x", (1.0, -1.0, -1.0)),
    ("invert", (-1.0, -1.0, -1.0)),
)

# vertices are matched on a grid this fine, in metres
SYMMETRY_GRID = 0.01
# at most this many vertices are checked per symmetry
SYMMETRY_SAMPLE = 20000

# {object id: {symmetry name: fraction of vertices it maps onto the mesh}}
_symmetry_cache = {}

# (object, correction) noted by swaps, applied when the tool finishes
_pending = []


def _relation(object_id):
    """(root id, mesh space matrix from the root's mesh) for an id, the way
    the library builds it - a variant from its root, anything else as itself."""
    if asset_library.REBUILD_VARIANTS:
        rebuild = variant_map.get_rebuild(object_id)
        if rebuild is not None:
            return rebuild
    return object_id, mathutils.Matrix.Identity(4)


def _is_identity(matrix):
    identity = mathutils.Matrix.Identity(4)
    return all(
        abs(matrix[row][column] - identity[row][column]) < TOLERANCE
        for row in range(4) for column in range(4)
    )


def _pack(grid):
    """Grid coordinates as one int64 each, for a fast membership test."""
    offset = 1 << 20
    grid = grid + offset
    return (grid[:, 0] << 42) | (grid[:, 1] << 21) | grid[:, 2]


def _symmetry_scores(object_id):
    """How well each candidate symmetry maps the id's library mesh onto
    itself, 0 to 1. Empty when the library has no mesh for it."""
    scores = _symmetry_cache.get(object_id)
    if scores is not None:
        return scores

    scores = {}
    mesh = asset_library.load_high_res_mesh(object_id)
    count = len(mesh.vertices) if mesh is not None else 0
    if count:
        coords = np.empty(count * 3, dtype=np.float64)
        mesh.vertices.foreach_get("co", coords)
        points = coords.reshape(-1, 3)
        grid = np.round(points / SYMMETRY_GRID).astype(np.int64)
        present = np.unique(_pack(grid))

        step = max(1, count // SYMMETRY_SAMPLE)
        sample = points[::step]
        for name, diagonal in _SYMMETRIES:
            mapped = np.round(sample * np.array(diagonal) / SYMMETRY_GRID).astype(np.int64)
            scores[name] = float(np.isin(_pack(mapped), present).mean())

    _symmetry_cache[object_id] = scores
    return scores


def twin_correction(from_id, to_id, kind=MIRROR):
    """What to post-multiply a twin's matrix by so it shows the part mirrored
    (or flipped) the way the addon means it.

    Args:
        from_id (str): The id the part had.
        to_id (str): Its twin's id.
        kind: MIRROR or FLIP.

    Returns:
        mathutils.Matrix: The 4x4 correction, or None when there is nothing
            to correct or it can't be known - a flip, or ids not built from a
            common root.
    """
    if kind != MIRROR:
        return None

    from_id = str(from_id).replace("^", "")
    to_id = str(to_id).replace("^", "")
    root_from, from_matrix = _relation(from_id)
    root_to, to_matrix = _relation(to_id)
    if root_from != root_to:
        return None

    relation = (to_matrix @ from_matrix.inverted()).to_3x3()
    flip = mathutils.Matrix.Diagonal(_MIRROR_FLIP)
    inverse_relation = relation.inverted()

    # a true mirror image needs no symmetry and no mesh to check it against
    exact = flip @ inverse_relation
    if exact.determinant() > 0:
        correction = exact
    else:
        scores = _symmetry_scores(from_id)
        best = None
        for name, diagonal in _SYMMETRIES:
            candidate = flip @ mathutils.Matrix.Diagonal(diagonal) @ inverse_relation
            if candidate.determinant() < 0:
                continue
            score = scores.get(name, 0.0)
            if best is None or score > best[0]:
                best = (score, candidate)
        if best is None:
            return None
        correction = best[1]

    correction = correction.to_4x4()
    if _is_identity(correction):
        return None
    return correction


# Swaps ---
def note_swap(bpy_object, correction):
    _pending.append((bpy_object, correction))


def discard_pending():
    _pending.clear()


def apply_pending():
    """Correct every twin swapped since the last call, where the tool left it."""
    try:
        for bpy_object, correction in _pending:
            try:
                bpy_object.matrix_world = bpy_object.matrix_world @ correction
            except ReferenceError:
                continue    # removed by the tool
    finally:
        _pending.clear()


# Groups ---
def correct_mirrored_cache(old_children, new_cache, object_id_key="ObjectID",
                           matrix_key="matrix_local"):
    """Correct a mirrored group cache's twins the same way.

    Args:
        old_children (dict): The cache before mirroring, {name: child data}.
        new_cache (str | dict): The mirrored cache, as json or parsed.

    Returns:
        str: The corrected cache, as json.
    """
    children = json.loads(new_cache) if isinstance(new_cache, str) else new_cache
    for name, cache_data in children.items():
        old = (old_children or {}).get(name)
        if not old or not cache_data.get(matrix_key):
            continue
        old_id, new_id = old.get(object_id_key), cache_data.get(object_id_key)
        if not old_id or not new_id or old_id == new_id:
            continue
        correction = twin_correction(old_id, new_id, MIRROR)
        if correction is None:
            continue
        matrix = mathutils.Matrix(cache_data[matrix_key]) @ correction
        cache_data[matrix_key] = [list(row) for row in matrix]
    return json.dumps(children)
