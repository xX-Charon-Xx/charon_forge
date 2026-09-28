"""Where a mirrored part's twin has to sit to look like the mirror.

The base builder addon mirrors a part by scaling its mesh by -1 along local X
and giving it the twin's id. A save only carries the id and the transform, so
the next import places the twin's OWN model with that transform - and that
only looks the same as the flipped mesh when the twin's model is the source's
scaled by -1 on X. Measured over the library, of the 267 mirror pairs with
both models:

  - 109 are exactly that (B_STR_T_NETB / B_STR_T_NWTB).
  - 118 are the same mirror, turned: the twin is the flipped source rotated
    about an axis - the corvette _N / _S pairs are turned 180 about up.
  - 40 are different geometry, with no rigid transform between them.

So a mirrored part shows its twin's own model (see
HighResBuilderMixin._swap_to_twin), and fit() is what places it: the rigid
transform that lays the twin's model over the source's X-flipped one, tried
over the 24 axis-aligned rotations. The addon mirrors the transform to
W @ M @ Sx (W the world reflection, Sx the local one) and then hands it to
mirror_correction; appending the fit there (host_patches) makes it
W @ M @ Sx @ fit, and with the twin's model B that draws as

    W @ M @ Sx @ fit @ B  =  W @ M @ Sx @ Sx @ A  =  W @ M @ A

- the exact mirror of the source A. What is drawn is then what is saved, so it
comes back the same on the next import.
"""

import itertools

import mathutils
import numpy as np
from mathutils.kdtree import KDTree

from . import asset_library

# The flip the addon applies to a part's mesh before it swaps the id.
_LOCAL_FLIP = np.array((-1.0, 1.0, 1.0))

# Enough points to tell 24 rotations apart without making the first mirror of
# a heavy part wait - the tree is capped, the probe is what is scored.
_TREE_POINTS = 20000
_PROBE_POINTS = 400

# How much better (mean distance, metres) a turned candidate has to score to
# beat the untouched one, so a symmetric part is never turned for nothing.
_TIE = 1e-4


def _proper_rotations():
    """The 24 axis-aligned rotations, identity first."""
    rotations = []
    for axes in itertools.permutations(range(3)):
        for signs in itertools.product((1.0, -1.0), repeat=3):
            rotation = np.zeros((3, 3))
            for row, (column, sign) in enumerate(zip(axes, signs)):
                rotation[row, column] = sign
            if np.linalg.det(rotation) > 0.0:
                rotations.append(rotation)
    return rotations


_ROTATIONS = _proper_rotations()

# {(source id, twin id): mathutils.Matrix or None}, per session
_fits = {}


def _vertices(object_id):
    mesh = asset_library.load_high_res_mesh(object_id)
    if mesh is None or not mesh.vertices:
        return None
    coords = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", coords)
    return coords.reshape(-1, 3)


def _every(points, count):
    return points[:: max(1, len(points) // count)]


def _bounds_centre(points):
    return (points.min(axis=0) + points.max(axis=0)) * 0.5


def _measure(source_id, twin_id):
    source = _vertices(source_id)
    twin = _vertices(twin_id)
    if source is None or twin is None:
        return None

    target = source * _LOCAL_FLIP
    tree_points = _every(target, _TREE_POINTS)
    tree = KDTree(len(tree_points))
    for index, point in enumerate(tree_points):
        tree.insert(point, index)
    tree.balance()

    probe = _every(twin, _PROBE_POINTS)
    target_centre = _bounds_centre(target)
    twin_centre = _bounds_centre(twin)
    zero = np.zeros(3)

    best = None
    for rotation in _ROTATIONS:
        turned = probe @ rotation.T
        # an axis-aligned turn keeps the bounds axis-aligned, so the turned
        # bounds' centre is the turned centre
        for offset in (zero, target_centre - rotation @ twin_centre):
            moved = turned + offset
            score = sum(tree.find(point)[2] for point in moved) / len(moved)
            if best is None or score < best[0] - _TIE:
                best = (score, rotation, offset)

    _, rotation, offset = best
    matrix = mathutils.Matrix.Identity(4)
    for row in range(3):
        for column in range(3):
            matrix[row][column] = rotation[row, column]
        matrix[row][3] = offset[row]
    return matrix


def fit(source_id, twin_id):
    """The mesh space transform that lays twin_id's model over source_id's
    model flipped on local X.

    Returns:
        mathutils.Matrix: A 4x4 rigid transform (a copy), or None when either
            id has no high res model to measure.
    """
    key = (source_id, twin_id)
    if key not in _fits:
        _fits[key] = _measure(source_id, twin_id)
    matrix = _fits[key]
    return matrix.copy() if matrix is not None else None


def clear():
    """Forget every fit, after the library meshes were reimported."""
    _fits.clear()
