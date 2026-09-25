"""Flat rectangles and squares made of copies of one part - the face filled
as rows, bricks, frames or a diagonal grid, and the edges lined with a band
of parts. Pure numpy, no Blender.

A rectangle lies on the XY plane about the origin. Like a circle
(utils/circle_topology.py) its face is measured by distance in from the
outline: the frames follow it inward, and the hole is whatever is deeper in
than the band, so the band is one width on every side.
"""

import math

import numpy as np

from .circle_topology import FLAT, WALL, _empty2, _flat_frames, _pitch, _wall_frames
from .shape_topology import _corner_to_corner as span

# how the face is filled
ROWS = "ROWS"
BRICK = "BRICK"
FRAMES = "FRAMES"
DIAGONAL = "DIAGONAL"


class Plate:
    """The face parts can go on: the rectangle less its margin and hole."""

    def __init__(self, width, height, margin=0.0, hole=0.0):
        self.half = np.array([width / 2, height / 2], dtype=np.float64)
        self.narrow = float(self.half.min())
        self.margin = float(margin)
        self.holed = hole > 1e-6
        # how far in from the outline the face goes - to the middle unholed
        self.depth = (1.0 - hole) * self.narrow if self.holed else self.narrow

    def hole_half(self, grow=0.0):
        """The hole's half width and height, grown by `grow`, or None."""
        if not self.holed:
            return None
        half = self.half - self.depth + grow
        return half if (half > 0).all() else None


def _segment(start, end, width, spacing):
    """Parts end to end from `start` to `end`, the first and last flush
    with them - with Spacing 0 or less, never a gap wider than it."""
    start, end = np.asarray(start, dtype=np.float64), np.asarray(end, dtype=np.float64)
    length = float(np.linalg.norm(end - start))
    if length <= 1e-9:
        return _empty2()
    direction = (end - start) / length
    centres = start + span(length, width, spacing)[:, None] * direction
    return centres, np.broadcast_to(direction, centres.shape).copy()


def _loop(half_x, half_y, width, height, spacing, flat, facing=1.0):
    """Parts round a rectangle's four sides, anticlockwise.

    Lying flat, the top and bottom run out over the corners and the sides
    fit between them, so the corners are covered once. Standing as walls,
    every side runs corner to corner.

    Returns:
        (centres, directions along the sides, directions away from the face)
    """
    reach = height / 2 if flat else 0.0
    sides = (
        ((-half_x - reach, -half_y), (half_x + reach, -half_y), (0.0, -1.0)),
        ((half_x, -half_y + reach), (half_x, half_y - reach), (1.0, 0.0)),
        ((half_x + reach, half_y), (-half_x - reach, half_y), (0.0, 1.0)),
        ((-half_x, half_y - reach), (-half_x, -half_y + reach), (-1.0, 0.0)),
    )
    centres, along, away = [], [], []
    for index, (start, end, out) in enumerate(sides):
        # a flat band too thin for its sides is only its top and bottom
        if index % 2 and half_y - reach <= 1e-9:
            continue
        # and one with no height is a single row
        if index == 2 and half_y <= 1e-9:
            continue
        points, directions = _segment(start, end, width, spacing)
        centres.append(points)
        along.append(directions)
        away.append(np.broadcast_to(np.array(out) * facing, points.shape))
    if not centres:
        return _empty2() + (np.zeros((0, 2)),)
    return np.concatenate(centres), np.concatenate(along), np.concatenate(away)


# Filling the face ---
def rows(plate, width, height, spacing, brick=False):
    """Straight rows, each running corner to corner across the face and
    split round the hole.

    As bricks, every other row sits half a part over. With Spacing 0 or less
    those rows also get a part flush with each end, so their ends aren't
    left with half-part gaps.
    """
    half_x, half_y = plate.half - plate.margin
    if half_x <= 0 or half_y <= 0:
        return _empty2() + ("",)
    # with a hole, the rows below it, beside it and above it are each fitted
    # edge to edge, so none straddles the hole's top or bottom
    hole = plate.hole_half(plate.margin)
    if hole is None or hole[1] >= half_y:
        bands = [(-half_y, half_y, False)]
    else:
        bands = [(-half_y, -hole[1], False), (-hole[1], hole[1], True), (hole[1], half_y, False)]
    lines = []
    for low, high, beside in bands:
        if high - low >= height / 2:
            lines += [(y, beside) for y in low + span(high - low, height, spacing)]

    centres = []
    for index, (y, beside) in enumerate(lines):
        pieces = [(-half_x, -hole[0]), (hole[0], half_x)] if beside else [(-half_x, half_x)]
        for start, end in pieces:
            length = end - start
            if length < width / 2:
                continue
            xs = start + span(length, width, spacing)
            if brick and index % 2 and len(xs) > 1:
                xs = (xs[1:] + xs[:-1]) / 2
                if spacing <= 0:
                    xs = np.concatenate([[start + width / 2], xs, [end - width / 2]])
            centres.append(np.stack([xs, np.full_like(xs, y)], axis=-1))
    if not centres:
        return _empty2() + ("",)
    centres = np.concatenate(centres)
    along = np.broadcast_to([1.0, 0.0], centres.shape).copy()
    return centres, along, "%d rows" % len(lines)


def frames(plate, width, height, spacing):
    """Rectangular frames following the outline in to the middle - or to
    the hole - each part lined up along its side, and a row down the long
    middle what the frames leave."""
    margin = plate.margin
    if plate.holed:
        band = plate.depth - 2 * margin
        if band <= 0:
            return _empty2() + ("",)
        depths = margin + span(band, height, spacing)
    else:
        band = plate.narrow - margin
        if band <= 0:
            return _empty2() + ("",)
        # the last one is at the very middle, where the core row goes
        depths = margin + span(band + height / 2, height, spacing)

    long_axis = int(np.argmax(plate.half))
    centres, along = [], []
    made = 0
    for index, depth in enumerate(depths):
        if not plate.holed and depth >= plate.narrow - 1e-9:
            inner = depths[index - 1] + height / 2 + max(spacing, 0.0) if index else margin
            reach = max(plate.half[long_axis] - inner, 0.0)
            direction = np.zeros(2)
            direction[long_axis] = 1.0
            points = (span(2 * reach, width, spacing) - reach)[:, None] * direction
            directions = np.broadcast_to(direction, points.shape).copy()
        else:
            half_x, half_y = plate.half - depth
            points, directions, _ = _loop(half_x, half_y, width, height, spacing, flat=True)
        if len(points):
            made += 1
            centres.append(points)
            along.append(directions)
    if not centres:
        return _empty2() + ("",)
    return np.concatenate(centres), np.concatenate(along), "%d frames" % made


def diagonal(plate, width, height, spacing):
    """A grid turned a quarter of the way round, keeping only the parts
    that fit whole."""
    half_x, half_y = plate.half - plate.margin
    if half_x <= 0 or half_y <= 0:
        return _empty2() + ("",)
    pitch_x, pitch_y = _pitch(width, spacing), _pitch(height, spacing)
    along = np.array([1.0, 1.0]) / math.sqrt(2)
    across = np.array([-1.0, 1.0]) / math.sqrt(2)
    extent = math.hypot(half_x, half_y)
    steps_x = np.arange(-math.ceil(extent / pitch_x), math.ceil(extent / pitch_x) + 1)
    steps_y = np.arange(-math.ceil(extent / pitch_y), math.ceil(extent / pitch_y) + 1)
    i, j = np.meshgrid(steps_x * pitch_x, steps_y * pitch_y)
    centres = i.ravel()[:, None] * along + j.ravel()[:, None] * across

    # how far a part turned this way reaches along X and along Y
    reach = (width + height) / (2 * math.sqrt(2))
    keep = (np.abs(centres[:, 0]) <= half_x - reach + 1e-9) & (
        np.abs(centres[:, 1]) <= half_y - reach + 1e-9
    )
    hole = plate.hole_half(plate.margin)
    if hole is not None:
        # separated from the hole along any one of the four axes
        overlaps = (
            (np.abs(centres[:, 0]) < hole[0] + reach)
            & (np.abs(centres[:, 1]) < hole[1] + reach)
            & (np.abs(centres @ along) < width / 2 + (hole[0] + hole[1]) / math.sqrt(2))
            & (np.abs(centres @ across) < height / 2 + (hole[0] + hole[1]) / math.sqrt(2))
        )
        keep &= ~overlaps
    centres = centres[keep]
    return centres, np.broadcast_to(along, centres.shape).copy(), ""


# Lining the edges ---
def rim(plate, width, height, spacing, offset=0.0, flat=True):
    """Parts lining the rectangle's edges - and the hole's - `offset` out
    from the face.

    Returns:
        (centres, directions along the edges, directions away from the face)
    """
    half_x, half_y = plate.half + offset
    pieces = []
    if half_x > 0 and half_y > 0:
        pieces.append(_loop(half_x, half_y, width, height, spacing, flat))
    hole = plate.hole_half(-offset)
    if hole is not None:
        pieces.append(_loop(hole[0], hole[1], width, height, spacing, flat, facing=-1.0))
    if not pieces:
        return _empty2() + (np.zeros((0, 2)),)
    return tuple(np.concatenate([piece[i] for piece in pieces]) for i in range(3))


def estimate(plate, width, height, spacing, faces_on, rim_on):
    """Roughly how many parts a layout needs, to refuse a huge one before
    building it."""
    pitch_x, pitch_y = _pitch(width, spacing), _pitch(height, spacing)
    half_x, half_y = np.maximum(plate.half - plate.margin, 0.0)
    total = 0.0
    if faces_on:
        total += 4 * half_x * half_y / (pitch_x * pitch_y)
    if rim_on:
        total += 4 * (plate.half.sum()) * (2 if plate.holed else 1) / pitch_x
    return total


def fill(plate, topology, width, height, spacing=0.0, faces_on=True, rim_on=False,
         rim_style=FLAT, rim_offset=0.0):
    """Every part's frame for a rectangle.

    Args:
        width, height: the room a part takes along and across its line.

    Returns:
        (centres, normals, along, up, a word on the face's layout)
    """
    groups = []
    detail = ""
    if faces_on:
        if topology == BRICK:
            centres, along, detail = rows(plate, width, height, spacing, brick=True)
        elif topology == FRAMES:
            centres, along, detail = frames(plate, width, height, spacing)
        elif topology == DIAGONAL:
            centres, along, detail = diagonal(plate, width, height, spacing)
        else:
            centres, along, detail = rows(plate, width, height, spacing)
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
