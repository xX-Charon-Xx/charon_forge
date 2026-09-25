"""Flat polygons made of copies of one part - the face filled as frames,
rows or wedges, and the edges lined with a band of parts. Pure numpy, no
Blender.

A polygon is any convex one, held as the lines along its sides: a regular
one with a flat bottom side, stretched along X and Y. Like a circle
(utils/circle_topology.py) its face is measured by distance in from the
outline: moving every side in by the same distance gives the line the
frames follow, and the hole is whatever is deeper in than the band, so the
band is one width on every side. Sides of a stretched polygon that shrink
away on the way in drop out.
"""

import functools
import math

import numpy as np

from .circle_topology import FLAT, WALL, _empty2, _flat_frames, _line_range, _pitch, _wall_frames
from .rectangle_topology import _segment
from .shape_topology import _corner_to_corner as span

# how the face is filled
FRAMES = "FRAMES"
ROWS = "ROWS"
WEDGES = "WEDGES"


def _perpendicular(vectors):
    return np.stack([-vectors[..., 1], vectors[..., 0]], axis=-1)


class Hull:
    """A convex polygon as the lines along its sides, anticlockwise: each
    side's outward unit normal and offset, inside where n.p <= c."""

    def __init__(self, vertices):
        self.vertices = np.asarray(vertices, dtype=np.float64)
        edges = np.roll(self.vertices, -1, axis=0) - self.vertices
        self.lengths = np.linalg.norm(edges, axis=1)
        self.tangents = edges / self.lengths[:, None]
        self.normals = -_perpendicular(self.tangents)
        self.offsets = (self.normals * self.vertices).sum(axis=1)
        self.centre = self.vertices.mean(axis=0)
        self.deepest, self.core = self._deepest()

    @classmethod
    def regular(cls, sides, radius, scale=(1.0, 1.0)):
        """A regular polygon with its corners `radius` from the middle and a
        flat side at the bottom, stretched by `scale`. Kept, since dragging
        any setting but these lays out the same polygon again."""
        return _regular(max(int(sides), 3), float(radius), tuple(float(s) for s in scale))

    def planes(self, depth):
        """The region `depth` in from the outline, for _line_range."""
        return self.normals, self.offsets - depth

    def inset(self, depth):
        """The polygon `depth` in from the outline - negative is outside it.

        Returns:
            (corners, the side each edge from a corner lies along) or None
            once nothing is that deep.
        """
        # each side's line moved in, and how much of it every other side's
        # line leaves: along side i from its foot, n_j.(p + s t_i) <= c_j
        offsets = self.offsets - depth
        feet = self.normals * offsets[:, None]
        room = offsets[None, :] - feet @ self.normals.T
        rate = self.tangents @ self.normals.T
        with np.errstate(divide="ignore", invalid="ignore"):
            reach = room / rate
        upper = np.where(rate > 1e-12, reach, np.inf).min(axis=1)
        lower = np.where(rate < -1e-12, reach, -np.inf).max(axis=1)
        # shut out altogether by a side facing the other way
        shut = ((np.abs(rate) <= 1e-12) & (room < -1e-9)).any(axis=1)
        sides = np.flatnonzero((upper - lower > 1e-9) & ~shut)
        if len(sides) < 3:
            return None
        return feet[sides] + self.tangents[sides] * lower[sides, None], sides

    def _deepest(self):
        """How far in the middle of the polygon is, and the point there."""
        low, high = 0.0, float((self.offsets - self.normals @ self.centre).min())
        if self.inset(high) is None:
            low, high = 0.0, high
        else:
            # the middle of the corners isn't always the deepest point
            low, high = high, float((self.offsets - self.normals @ self.centre).max())
        for _ in range(32):
            middle = (low + high) / 2
            if self.inset(middle) is None:
                high = middle
            else:
                low = middle
        found = self.inset(low)
        return low, (found[0].mean(axis=0) if found is not None else self.centre)

    def area(self, depth=0.0):
        found = self.inset(depth)
        if found is None:
            return 0.0
        x, y = found[0][:, 0], found[0][:, 1]
        return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


@functools.lru_cache(maxsize=16)
def _regular(sides, radius, scale):
    angles = -math.pi / 2 - math.pi / sides + np.arange(sides) * 2 * math.pi / sides
    corners = radius * np.stack([np.cos(angles), np.sin(angles)], axis=-1)
    return Hull(corners * np.asarray(scale, dtype=np.float64))


class Plate:
    """The face parts can go on: the polygon less its margin and hole."""

    def __init__(self, hull, margin=0.0, hole=0.0):
        self.hull = hull
        self.margin = float(margin)
        self.holed = hole > 1e-6
        # how far in from the outline the face goes - to the middle unholed
        self.depth = (1.0 - hole) * hull.deepest if self.holed else hull.deepest


def _band(hull, depth, width, height, spacing, flat, facing=1.0, inner_edge=False):
    """Parts along every side of the polygon `depth` in, each side's run
    lined up with it.

    Lying flat with Spacing 0 or less, each side's run reaches as far as the
    band's longer edge, the one nearer the outline, so its corners are
    covered - at a sharp corner that reaches a little past it. Otherwise it
    runs corner to corner along its line, or with `inner_edge` only as far
    as the band's shorter edge, so neighbouring sides never overlap.

    Returns:
        (centres, directions along the sides, directions away from the face)
    """
    found = hull.inset(depth)
    if found is None:
        return _empty2() + (np.zeros((0, 2)),)
    corners, sides = found
    ends = np.roll(corners, -1, axis=0)
    reach = {}
    measured = None
    if flat and spacing <= 0:
        measured = depth - height / 2
    elif flat and inner_edge:
        measured = depth + height / 2
    if measured is not None:
        wider = hull.inset(measured)
        if wider is not None:
            wide_corners, wide_sides = wider
            wide_ends = np.roll(wide_corners, -1, axis=0)
            reach = {side: (wide_corners[k], wide_ends[k]) for k, side in enumerate(wide_sides)}

    centres, along, away = [], [], []
    for k, side in enumerate(sides):
        start, end = corners[k], ends[k]
        tangent, normal = hull.tangents[side], hull.normals[side]
        if side in reach:
            # the wider edge's ends, brought onto this side's line
            level = normal @ start
            start = reach[side][0] - normal * (normal @ reach[side][0] - level)
            end = reach[side][1] - normal * (normal @ reach[side][1] - level)
        if (end - start) @ tangent <= 1e-9:
            continue
        points, directions = _segment(start, end, width, spacing)
        centres.append(points)
        along.append(directions)
        away.append(np.broadcast_to(normal * facing, points.shape))
    if not centres:
        return _empty2() + (np.zeros((0, 2)),)
    return np.concatenate(centres), np.concatenate(along), np.concatenate(away)


def _core(plate, depth, width, spacing):
    """A row down the longest way across what the frames leave in the
    middle - one part in a regular polygon."""
    found = plate.hull.inset(min(depth, plate.hull.deepest))
    if found is None or len(found[0]) < 2:
        centre = plate.hull.core
        return centre[None, :], np.array([[1.0, 0.0]])
    corners = found[0]
    gaps = corners[:, None, :] - corners[None, :, :]
    first, second = np.unravel_index(np.argmax((gaps ** 2).sum(axis=-1)), gaps.shape[:2])
    start, end = corners[second], corners[first]
    length = float(np.linalg.norm(end - start))
    if length <= width:
        direction = (end - start) / length if length > 1e-9 else np.array([1.0, 0.0])
        return ((start + end) / 2)[None, :], direction[None, :]
    direction = (end - start) / length
    centres = start + span(length, width, spacing)[:, None] * direction
    return centres, np.broadcast_to(direction, centres.shape).copy()


# Filling the face ---
def frames(plate, width, height, spacing):
    """Frames following the sides in to the middle - or to the hole - each
    part lined up along its side, and a row across what they leave."""
    margin = plate.margin
    hull = plate.hull
    if plate.holed:
        band = plate.depth - 2 * margin
        if band <= 0:
            return _empty2() + ("",)
        depths = margin + span(band, height, spacing)
    else:
        band = hull.deepest - margin
        if band <= 0:
            return _empty2() + ("",)
        # the last one is at the very middle, where the core row goes
        depths = margin + span(band + height / 2, height, spacing)

    centres, along = [], []
    made = 0
    for index, depth in enumerate(depths):
        if not plate.holed and depth >= hull.deepest - 1e-9:
            inner = depths[index - 1] + height / 2 + max(spacing, 0.0) if index else margin
            points, directions = _core(plate, inner, width, spacing)
        else:
            points, directions, _ = _band(hull, depth, width, height, spacing, flat=True,
                                          inner_edge=True)
        if len(points):
            made += 1
            centres.append(points)
            along.append(directions)
    if not centres:
        return _empty2() + ("",)
    return np.concatenate(centres), np.concatenate(along), "%d frames" % made


def rows(plate, width, height, spacing):
    """Straight rows, each as long as fits across the face, whole parts
    only, and split round the hole."""
    hull = plate.hull
    outer = hull.inset(plate.margin)
    if outer is None:
        return _empty2() + ("",)
    region = hull.planes(plate.margin)
    bottom, top = outer[0][:, 1].min(), outer[0][:, 1].max()

    hole_region = hole_corners = None
    bands = [(bottom, top)]
    if plate.holed:
        found = hull.inset(plate.depth - plate.margin)
        if found is not None:
            hole_region = hull.planes(plate.depth - plate.margin)
            hole_corners = found[0]
            # the rows below the hole, beside it and above it each fitted
            # edge to edge, so none straddles its top or bottom
            low, high = hole_corners[:, 1].min(), hole_corners[:, 1].max()
            bands = [(bottom, low), (low, high), (high, top)]
    lines = []
    for low, high in bands:
        if high - low >= height / 2:
            lines += list(low + span(high - low, height, spacing))
    ys = np.array(lines)
    if not len(ys):
        return _empty2() + ("",)

    across = np.array([1.0, 0.0])
    lower = np.stack([np.zeros_like(ys), ys - height / 2], axis=-1)
    upper = np.stack([np.zeros_like(ys), ys + height / 2], axis=-1)
    low0, high0, in0 = _line_range(region, lower, across)
    low1, high1, in1 = _line_range(region, upper, across)
    starts = np.maximum(low0, low1) + width / 2
    ends = np.minimum(high0, high1) - width / 2

    centres = []
    for row in np.flatnonzero(in0 & in1 & (starts <= ends + 1e-9)):
        pieces = [(starts[row], ends[row])]
        if hole_region is not None:
            blocked = _hole_span(hole_region, hole_corners, ys[row], height)
            if blocked is not None:
                pieces = [(starts[row], min(ends[row], blocked[0] - width / 2)),
                          (max(starts[row], blocked[1] + width / 2), ends[row])]
        for start, end in pieces:
            if end < start - 1e-9:
                continue
            xs = start - width / 2 + span(end - start + width, width, spacing)
            centres.append(np.stack([xs, np.full_like(xs, ys[row])], axis=-1))
    if not centres:
        return _empty2() + ("",)
    centres = np.concatenate(centres)
    along = np.broadcast_to([1.0, 0.0], centres.shape).copy()
    return centres, along, "%d rows" % len(ys)


def _hole_span(hole_region, hole_corners, y, height):
    """How far along X the hole reaches within a row's height, or None."""
    lines = np.array([[0.0, y - height / 2], [0.0, y + height / 2]])
    low, high, crossed = _line_range(hole_region, lines, np.array([1.0, 0.0]))
    xs = list(low[crossed]) + list(high[crossed])
    within = np.abs(hole_corners[:, 1] - y) <= height / 2 + 1e-7
    xs += list(hole_corners[within, 0])
    if not xs:
        return None
    return min(xs), max(xs)


def wedges(plate, width, height, spacing):
    """A wedge from the middle to each side, filled with rows along that
    side that shorten towards the middle, and a part at the middle.

    With Spacing 0 or less a row is as long as the wedge at its outer edge,
    reaching over the seams to the next wedge so none opens up; above 0 as
    long as at its inner edge, so the wedges stay apart.
    """
    hull = plate.hull
    margin = plate.margin
    if hull.deepest - margin <= 0:
        return _empty2() + ("",)
    apex = hull.centre
    region = hull.planes(margin)
    centres, along = [], []
    for side in range(len(hull.normals)):
        normal, tangent = hull.normals[side], hull.tangents[side]
        first, last = hull.vertices[side], np.roll(hull.vertices, -1, axis=0)[side]
        # how far the middle is from this side
        apothem = hull.offsets[side] - normal @ apex
        if apothem <= 1e-9:
            continue
        if plate.holed:
            band = plate.depth - 2 * margin
            if band <= 0:
                continue
            distances = margin + span(band, height, spacing)
        else:
            if apothem - margin <= 0:
                continue
            distances = margin + span(apothem - margin, height, spacing)
        for distance in distances:
            measured = distance - height / 2 if spacing <= 0 else distance + height / 2
            fraction = min(max(measured / apothem, 0.0), 1.0)
            # the wedge's width at the measured edge, brought onto the row
            shift = -normal * (distance - measured)
            start = first + (apex - first) * fraction + shift
            end = last + (apex - last) * fraction + shift
            # kept inside the outline - where the seams from the middle
            # don't halve a stretched polygon's corners, the wedge alone
            # would let a row out past the next side. With Spacing 0 or less
            # it may reach out half a part, like the rows beside it.
            across = [0.0] if spacing <= 0 else [-height / 2, height / 2]
            lines = start + np.outer(across, -normal)
            low, high, inside = _line_range(region, lines, tangent)
            if not inside.all():
                continue
            length = (end - start) @ tangent
            cut_start, cut_end = max(low.max(), 0.0), min(high.min(), length)
            start, end = start + tangent * cut_start, start + tangent * cut_end
            length = cut_end - cut_start
            if length < (width / 2 if spacing <= 0 else width) - 1e-9:
                continue
            points, directions = _segment(start, end, width, spacing)
            centres.append(points)
            along.append(directions)
    if not plate.holed and margin < hull.deepest:
        centres.append(apex[None, :])
        along.append(np.array([[1.0, 0.0]]))
    if not centres:
        return _empty2() + ("",)
    return np.concatenate(centres), np.concatenate(along), "%d wedges" % len(hull.normals)


# Lining the edges ---
def rim(plate, width, height, spacing, offset=0.0, flat=True):
    """Parts lining the polygon's sides - and the hole's - `offset` out
    from the face.

    Returns:
        (centres, directions along the sides, directions away from the face)
    """
    pieces = [_band(plate.hull, -offset, width, height, spacing, flat)]
    if plate.holed:
        pieces.append(_band(plate.hull, plate.depth + offset, width, height, spacing, flat,
                            facing=-1.0))
    return tuple(np.concatenate([piece[i] for piece in pieces]) for i in range(3))


def estimate(plate, width, height, spacing, faces_on, rim_on):
    """Roughly how many parts a layout needs, to refuse a huge one before
    building it."""
    pitch_x, pitch_y = _pitch(width, spacing), _pitch(height, spacing)
    total = 0.0
    if faces_on:
        total += plate.hull.area(plate.margin) / (pitch_x * pitch_y)
    if rim_on:
        total += plate.hull.lengths.sum() * (2 if plate.holed else 1) / pitch_x
    return total


def fill(plate, topology, width, height, spacing=0.0, faces_on=True, rim_on=False,
         rim_style=FLAT, rim_offset=0.0):
    """Every part's frame for a polygon.

    Args:
        width, height: the room a part takes along and across its line.

    Returns:
        (centres, normals, along, up, a word on the face's layout)
    """
    groups = []
    detail = ""
    if faces_on:
        if topology == ROWS:
            centres, along, detail = rows(plate, width, height, spacing)
        elif topology == WEDGES:
            centres, along, detail = wedges(plate, width, height, spacing)
        else:
            centres, along, detail = frames(plate, width, height, spacing)
        groups.append(_flat_frames(centres, along))
    if rim_on:
        centres, along, away = rim(plate, width, height, spacing, rim_offset,
                                   flat=rim_style != WALL)
        if rim_style == WALL:
            groups.append(_wall_frames(centres, away, height))
        else:
            groups.append(_flat_frames(centres, along))
    if not groups:
        empty = np.zeros((0, 3))
        return empty, empty, empty, empty, detail
    return tuple(np.concatenate([group[i] for group in groups]) for i in range(4)) + (detail,)
