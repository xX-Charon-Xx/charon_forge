"""Triangular parts in the Forge's layouts - a triangle floor, say.

Every layout lays the part out as if it were the rectangle round it, which
leaves a triangle's worth of gap in every cell. Triangles tile a row instead
as up and down in turn: every copy the layout places stays where it is, and
one turned half round about its face goes into each gap between it and the
next copy along its row - or, for a right triangle, into the other half of
its own cell. Each row is then covered all the way along, whichever way its
neighbours sit, so it works on anything laid in rows: straight rows, bricks,
frames, rings, spokes, the faces of a shape.

A part's centre is the middle of the rectangle round it, which is what a
layout puts on each point, so the turned copies only need their own centres
worked out. Pure numpy, no Blender.
"""

import numpy as np

from ...utils.frames import unit as _unit

RECTANGLE = "RECTANGLE"
TRIANGLE = "TRIANGLE"

# a hull turning by less than this at a corner has no corner there, radians
_STRAIGHT = np.radians(8.0)

# a triangle covers half the rectangle round it; let a bevelled one off
_HALF = (0.4, 0.6)

# how far off lined up with the rectangle a side may be and still be its base
_ALIGNED = 0.03


class Footprint:
    """What a triangle part looks like from above, in the two axes it lies
    along: which of them its base runs along (0 or 1), how far along the
    base its tip is (0 at the base's low end, 1 at the high end), and which
    way the tip is from the base along the other axis (+1 or -1)."""

    def __init__(self, base_axis, tip, side):
        self.base_axis = base_axis
        self.tip = tip
        self.side = side


def _hull(points):
    """The convex hull of 2D points, anticlockwise - Andrew's monotone chain."""
    points = np.unique(np.round(np.asarray(points, dtype=np.float64), 6), axis=0)
    if len(points) < 3:
        return points

    def half(ordered):
        chain = []
        for point in ordered:
            while len(chain) >= 2:
                (ax, ay), (bx, by) = chain[-2], chain[-1]
                if (bx - ax) * (point[1] - ay) - (by - ay) * (point[0] - ax) > 1e-12:
                    break
                chain.pop()
            chain.append(point)
        return chain

    lower, upper = half(points), half(points[::-1])
    return np.array(lower[:-1] + upper[:-1])


def _corners(hull):
    """The hull with its near-straight corners and tiny sides taken out."""
    corners = list(hull)
    perimeter = float(np.sum(np.linalg.norm(np.roll(hull, -1, axis=0) - hull, axis=1)))
    changed = True
    while changed and len(corners) > 3:
        changed = False
        for index in range(len(corners)):
            before, here = corners[index - 1], corners[index]
            after = corners[(index + 1) % len(corners)]
            into, out = here - before, after - here
            turn = abs(np.arctan2(into[0] * out[1] - into[1] * out[0], into @ out))
            if turn < _STRAIGHT or min(np.linalg.norm(into), np.linalg.norm(out)) < 0.03 * perimeter:
                del corners[index]
                changed = True
                break
    return np.array(corners)


def detect(points):
    """The part's footprint if it is a triangle - `points` its corners as
    seen from above, in the two axes it lies along - or None.

    It has to be one with a side lined up with the rectangle round it, to
    lie along the layout's rows; a triangle turned at an angle is left a
    rectangle.
    """
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 3:
        return None
    low, high = points.min(axis=0), points.max(axis=0)
    size = high - low
    if (size <= 1e-9).any():
        return None
    hull = _hull(points)
    if len(hull) < 3:
        return None
    x, y = hull[:, 0], hull[:, 1]
    area = 0.5 * abs(x @ np.roll(y, -1) - y @ np.roll(x, -1))
    if not _HALF[0] <= area / (size[0] * size[1]) <= _HALF[1]:
        return None

    corners = _corners(hull)
    if len(corners) != 3:
        return None
    for index in range(3):
        start, end = corners[index], corners[(index + 1) % 3]
        tip = corners[(index + 2) % 3]
        side = (end - start) / size
        for base_axis in (0, 1):
            across = 1 - base_axis
            if abs(side[across]) < _ALIGNED:
                along = (tip[base_axis] - low[base_axis]) / size[base_axis]
                way = 1.0 if tip[across] > start[across] else -1.0
                return Footprint(base_axis, float(np.clip(along, 0.0, 1.0)), way)
    return None


# Laying them ---
def interleave(centres, normals, along, up, base, tip, closed=True):
    """The layout's copies with a copy turned half round in every gap a
    triangle leaves along its rows.

    Args:
        centres, normals, along, up (N x 3): the copies, in the order the
            layout made them - one row after another.
        base (float or N): how long each copy's base is, along its row.
        tip (float): how far along the base the tip is, 0 to 1.
        closed (bool): a row whose ends meet - a whole ring - gets a copy
            across the seam.

    Returns:
        (centres, normals, along, up, which copy each came from)
    """
    centres = np.asarray(centres, dtype=np.float64)
    count = len(centres)
    source = np.arange(count)
    if count == 0:
        return centres, normals, along, up, source
    base = np.broadcast_to(np.asarray(base, dtype=np.float64), (count,))

    if tip <= 0.25 or tip >= 0.75:
        # a right triangle, near enough: the turned copy is in the other half
        # of each copy's own cell, and fills it
        shift = (tip if tip <= 0.25 else tip - 1.0) * base
        extra = (centres + shift[:, None] * along, normals, -along, -up, source)
    else:
        pairs = _neighbours(centres, normals, along, base, closed)
        if not len(pairs):
            return centres, normals, along, up, source
        first, second = pairs[:, 0], pairs[:, 1]
        extra = (
            centres[first] + tip * (centres[second] - centres[first]),
            _unit(normals[first] + normals[second]),
            -_unit(along[first] + along[second]),
            -_unit(up[first] + up[second]),
            first,
        )
    return tuple(np.concatenate([whole, part]) for whole, part in zip(
        (centres, normals, along, up, source), extra
    ))


def _neighbours(centres, normals, along, base, closed):
    """(behind, ahead) for every two copies side by side in a row - each
    after the other in the layout's order, lying the same way, one about a
    base on from the other along it."""
    def beside(a, b):
        offset = centres[b] - centres[a]
        forward = np.einsum("ij,ij->i", offset, along[a])
        sideways = np.linalg.norm(offset - forward[:, None] * along[a], axis=1)
        # a tight ring turns a copy a good way from the next - but never a
        # frame's corner, a quarter turn
        same = (np.einsum("ij,ij->i", along[a], along[b]) > 0.7) & (
            np.einsum("ij,ij->i", normals[a], normals[b]) > 0.7
        )
        near = (np.abs(forward) > 0.5 * base[a]) & (np.abs(forward) < 1.75 * base[a])
        return same & near & (sideways < 0.4 * base[a]), forward

    count = len(centres)
    index = np.arange(count - 1)
    joined, forward = beside(index, index + 1)
    # ordered so the second is ahead of the first along the row
    pairs = [np.where(forward[joined, None] > 0,
                      np.stack([index[joined], index[joined] + 1], axis=-1),
                      np.stack([index[joined] + 1, index[joined]], axis=-1))]

    if closed:
        # a row running all the way round comes back to its start
        starts = np.flatnonzero(np.concatenate([[True], ~joined]))
        ends = np.concatenate([starts[1:] - 1, [count - 1]])
        long_rows = ends - starts >= 2
        if long_rows.any():
            last, first = ends[long_rows], starts[long_rows]
            seam, forward = beside(last, first)
            pairs.append(np.where(forward[seam, None] > 0,
                                  np.stack([last[seam], first[seam]], axis=-1),
                                  np.stack([first[seam], last[seam]], axis=-1)))
    return np.concatenate(pairs) if pairs else np.zeros((0, 2), dtype=int)


def geodesic_faces(corners, faces, frequency, side):
    """A copy on every face of an icosahedron cut `frequency` times along
    each edge and pushed out onto the unit sphere - the faces are all but
    equilateral, so a triangle part fits each one.

    Args:
        corners, faces: the icosahedron.
        side (+1 or -1): which way the part's tip is from its base, along
            its up.

    Returns:
        (normals, along, up), one each per face, the part's base along a
        side of its face and its tip towards the corner across from it.
    """
    frequency = max(1, int(frequency))
    triangles = []
    for i in range(frequency):
        for j in range(frequency - i):
            triangles.append(((i, j), (i + 1, j), (i, j + 1)))
            if i + j < frequency - 1:
                triangles.append(((i + 1, j), (i + 1, j + 1), (i, j + 1)))
    steps = np.array(triangles, dtype=np.float64) / frequency         # T x 3 x 2
    a, b, c = (corners[faces[:, k]] for k in range(3))                  # F x 3
    points = (a[:, None, None] + (b - a)[:, None, None] * steps[None, :, :, 0:1]
              + (c - a)[:, None, None] * steps[None, :, :, 1:2])
    points = _unit(points.reshape(-1, 3, 3))

    start, end, tip = points[:, 0], points[:, 1], points[:, 2]
    middle = (start + end) / 2
    along = _unit(end - start)
    towards = tip - middle
    towards = towards - np.einsum("ij,ij->i", towards, along)[:, None] * along
    # the middle of the rectangle round the part: over the middle of its
    # base, halfway to its tip
    normals = _unit(middle + towards / 2)
    along = _unit(along - np.einsum("ij,ij->i", along, normals)[:, None] * normals)
    up = np.cross(normals, along)
    # its tip towards the corner across, turning it half round if not
    turn = np.where(np.einsum("ij,ij->i", up, towards) * side < 0, -1.0, 1.0)[:, None]
    return normals, along * turn, up * turn
