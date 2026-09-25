"""Flat circles made of copies of one part - the face filled as rings, rows, a
grid, spokes, spiral arms or a sunflower spread, and the outline lined with a
band of parts. Pure numpy, no Blender.

A circle lies on the XY plane about the origin, stretched into an ellipse
with semi-axes `a` along X and `b` along Y. Its face is measured by distance
in from the outline, so the margin, the rings and the hole keep one width all
the way round an ellipse the way they do round a circle: each ring follows
the line a set distance in (`level_curve`), and the hole is everything
deeper in than the band.
"""

import math

import numpy as np

from .frames import unit
from .shape_topology import _corner_to_corner as span

FULL_TURN = 2 * math.pi
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))

# points round every outline; the parts are laid by length along it, so this
# only sets how closely a curve is followed
SAMPLES = 1024

# how the face is filled
RINGS = "RINGS"
ROWS = "ROWS"
GRID = "GRID"
SPOKES = "SPOKES"
SPIRAL = "SPIRAL"
SUNFLOWER = "SUNFLOWER"
# the patterns Centre Density works on
DENSITY_TOPOLOGIES = (RINGS, SPIRAL, SUNFLOWER)

# how the parts round the outline sit
FLAT = "FLAT"
WALL = "WALL"

_Z = np.array([0.0, 0.0, 1.0])


def _empty2():
    return np.zeros((0, 2)), np.zeros((0, 2))


def _perpendicular(vectors):
    """Each 2D vector turned a quarter turn anticlockwise."""
    return np.stack([-vectors[..., 1], vectors[..., 0]], axis=-1)


def _pitch(size, spacing):
    return max(size + spacing, 0.05 * size, 1e-6)


def _loop_count(length, size, spacing):
    """How many parts go round a closed loop. With Spacing above 0 as many as
    fit at least that far apart; otherwise enough that no gap is wider than
    Spacing, so the loop never opens up."""
    pitch = _pitch(size, spacing)
    if spacing > 0:
        count = math.floor(length / pitch + 1e-9)
    else:
        count = math.ceil(length / pitch - 1e-9)
    return max(int(count), 1)


def _runs(mask):
    """(first, last) index of every stretch of True in `mask`."""
    edges = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1) - 1)


# Curves ---
def level_curve(a, b, depth, samples=SAMPLES):
    """The line `depth` in from the ellipse's outline, anticlockwise from
    the +X side - negative depth is outside it.

    Each outline point is moved in along its normal. Deeper than the
    outline's curvature at the ends of the long axis, those moves cross over,
    and the points past the long axis are left out: what remains is the true
    line at that distance, closing to a point at the middle.
    """
    t = np.linspace(0.0, FULL_TURN, samples, endpoint=False)
    cos, sin = np.cos(t), np.sin(t)
    outward = unit(np.stack([b * cos, a * sin], axis=-1))
    curve = np.stack([a * cos, b * sin], axis=-1) - depth * outward
    # how far in each normal goes before it crosses the long axis
    reach = min(a, b) * np.hypot(b * cos, a * sin) / max(a, b)
    return curve[depth <= reach + 1e-12]


def _walk(points, closed):
    ends = np.vstack([points, points[:1]]) if closed else points
    steps = np.diff(ends, axis=0)
    lengths = np.linalg.norm(steps, axis=1)
    return ends, steps, lengths, np.concatenate([[0.0], np.cumsum(lengths)])


def _length(points, closed):
    return _walk(points, closed)[3][-1]


def _sample(points, closed, positions):
    """Points and unit directions at distances along a polyline."""
    ends, steps, lengths, travelled = _walk(points, closed)
    positions = np.clip(np.asarray(positions, dtype=np.float64), 0.0, travelled[-1])
    index = np.clip(np.searchsorted(travelled, positions, side="right") - 1, 0, len(steps) - 1)
    fraction = (positions - travelled[index]) / np.where(lengths[index] > 0, lengths[index], 1.0)
    return ends[index] + steps[index] * fraction[:, None], unit(steps[index])


def _polygon(a, b, depth):
    """The region at least `depth` in from the outline, as the edges of a
    convex polygon: outward normals and offsets, inside where n.p <= c."""
    curve = level_curve(a, b, depth)
    if len(curve) < 3:
        return None
    edges = np.roll(curve, -1, axis=0) - curve
    normals = np.stack([edges[:, 1], -edges[:, 0]], axis=-1)
    return normals, (normals * curve).sum(axis=1)


def _line_range(polygon, origins, directions):
    """Where each line origin + r * direction is inside a convex polygon:
    (lowest r, highest r, whether it goes in at all)."""
    normals, offsets = polygon
    origins = np.atleast_2d(origins)
    directions = np.broadcast_to(directions, origins.shape)
    room = offsets[None, :] - origins @ normals.T
    rate = directions @ normals.T
    with np.errstate(divide="ignore", invalid="ignore"):
        r = room / rate
    upper = np.where(rate > 1e-12, r, np.inf).min(axis=1)
    lower = np.where(rate < -1e-12, r, -np.inf).max(axis=1)
    # a line along an edge counts as in
    missed = ((np.abs(rate) <= 1e-12) & (room < -1e-9)).any(axis=1)
    return lower, upper, (lower <= upper) & ~missed


def _rect_points(centres, along, width, height):
    """A part's corners, edge middles and centre - 9 points each."""
    across = _perpendicular(along)
    steps = np.array([-0.5, 0.0, 0.5])
    u, v = np.meshgrid(steps * width, steps * height)
    return (
        centres[:, None, :]
        + u.ravel()[None, :, None] * along[:, None, :]
        + v.ravel()[None, :, None] * across[:, None, :]
    )


class Disc:
    """The face parts can go on: the ellipse, less its margin and hole, cut
    to its sweep (anticlockwise from +X)."""

    def __init__(self, a, b, margin=0.0, hole=0.0, sweep=FULL_TURN):
        self.a, self.b = float(a), float(b)
        self.narrow, self.wide = min(self.a, self.b), max(self.a, self.b)
        self.margin = float(margin)
        self.holed = hole > 1e-6
        # how far in from the outline the face goes - to the middle unholed
        self.depth = (1.0 - hole) * self.narrow if self.holed else self.narrow
        self.sweep = float(min(max(sweep, 1e-6), FULL_TURN))
        self.whole = self.sweep >= FULL_TURN - 1e-6
        self.rays = np.array([[1.0, 0.0], [math.cos(self.sweep), math.sin(self.sweep)]])

    def in_sector(self, points, clearance=0.0):
        """Whether each point is inside the sweep, at least `clearance` from
        its two straight edges."""
        if self.whole:
            return np.ones(points.shape[:-1], dtype=bool)
        angle = np.mod(np.arctan2(points[..., 1], points[..., 0]), FULL_TURN)
        radius = np.linalg.norm(points, axis=-1)
        inside = (angle <= self.sweep + 1e-9) | (angle >= FULL_TURN - 1e-9) | (radius < 1e-9)
        if clearance > 0:
            for ray in self.rays:
                gap = np.where(
                    points @ ray >= 0,
                    np.abs(points[..., 0] * ray[1] - points[..., 1] * ray[0]),
                    radius,
                )
                inside &= gap >= clearance - 1e-9
        return inside

    def rects_in_sector(self, centres, along, width, height):
        if self.whole or not len(centres):
            return np.ones(len(centres), dtype=bool)
        points = _rect_points(centres, along, width, height)
        return self.in_sector(points, max(self.margin, 0.0)).all(axis=1)


# Filling the face ---
def rings(disc, width, height, spacing, stagger=False, density=0.0):
    """Rings following the outline in to the middle - or to the hole - each
    holding as many parts as go round it, lined up along it.

    Flat parts round a tight ring touch at their inner edges and fan apart at
    their outer ones. `density` counts each ring by a line that far out, in
    half part heights - 1 is the parts' outer edges, which closes those
    wedges - so the tight rings in the middle gain parts and the wide outer
    ones hardly change.
    """
    margin = disc.margin
    if disc.holed:
        # the margin keeps the parts off the hole's edge too
        band = disc.depth - 2 * margin
        if band <= 0:
            return _empty2() + ("",)
        depths = margin + span(band, height, spacing)
    else:
        band = disc.narrow - margin
        if band <= 0:
            return _empty2() + ("",)
        # the last one is at the very middle, where the core row goes
        depths = margin + span(band + height / 2, height, spacing)

    clearance = width / 2 + max(margin, 0.0)
    centres, along = [], []
    made = 0
    for index, depth in enumerate(depths):
        if not disc.holed and depth >= disc.narrow - 1e-9:
            inner = depths[index - 1] + height / 2 + max(spacing, 0.0) if index else margin
            points, directions = _core(disc, inner, width, height, spacing)
        else:
            curve = level_curve(disc.a, disc.b, depth)
            if len(curve) < 3:
                continue
            # how much longer the line the ring is counted by is
            stretch = 1.0
            if density > 0:
                counted = level_curve(disc.a, disc.b, depth - density * height / 2)
                stretch = max(_length(counted, True) / max(_length(curve, True), 1e-9), 1.0)
            if disc.whole:
                length = _length(curve, True)
                count = _loop_count(length * stretch, width, spacing)
                shift = 0.5 if stagger and index % 2 else 0.0
                points, directions = _sample(
                    curve, True, (np.arange(count) + shift) * length / count
                )
            else:
                inside = np.flatnonzero(disc.in_sector(curve, clearance))
                if not len(inside):
                    continue
                run = curve[inside[0]:inside[-1] + 1]
                length = _length(run, False) * stretch
                points, directions = _sample(
                    run, False, (span(length + width, width, spacing) - width / 2) / stretch
                )
        if len(points):
            made += 1
            centres.append(points)
            along.append(directions)
    if not centres:
        return _empty2() + ("",)
    return np.concatenate(centres), np.concatenate(along), "%d rings" % made


def _core(disc, depth, width, height, spacing):
    """A row along the long axis over what the rings leave in the middle -
    one part for a circle, a line of them down a long ellipse."""
    axis = np.array([1.0, 0.0]) if disc.a >= disc.b else np.array([0.0, 1.0])
    curve = level_curve(disc.a, disc.b, min(depth, disc.narrow))
    reach = float(np.abs(curve @ axis).max()) if len(curve) else 0.0
    centres = (span(2 * reach, width, spacing) - reach)[:, None] * axis
    along = np.broadcast_to(axis, centres.shape).copy()
    keep = disc.rects_in_sector(centres, along, width, height)
    return centres[keep], along[keep]


def _row_runs(disc, ys, width, height):
    """The stretches of x each row's part centres can go along, whole parts
    staying inside the face: (row, start, end)."""
    outer = _polygon(disc.a, disc.b, disc.margin)
    if outer is None:
        return []
    across = np.array([1.0, 0.0])
    lower = np.stack([np.zeros_like(ys), ys - height / 2], axis=-1)
    upper = np.stack([np.zeros_like(ys), ys + height / 2], axis=-1)
    low0, high0, in0 = _line_range(outer, lower, across)
    low1, high1, in1 = _line_range(outer, upper, across)
    starts = np.maximum(low0, low1) + width / 2
    ends = np.minimum(high0, high1) - width / 2
    fits = in0 & in1 & (starts <= ends + 1e-9)

    # the hole is widest across a row where the row is nearest the middle
    blocked = None
    if disc.holed:
        hole = _polygon(disc.a, disc.b, disc.depth - disc.margin)
        if hole is not None:
            nearest = np.clip(0.0, ys - height / 2, ys + height / 2)
            hole_low, hole_high, crossed = _line_range(
                hole, np.stack([np.zeros_like(ys), nearest], axis=-1), across
            )
            blocked = (hole_low - width / 2, hole_high + width / 2, crossed)

    runs = []
    for row in np.flatnonzero(fits):
        pieces = [(starts[row], ends[row])]
        if blocked is not None and blocked[2][row]:
            pieces = [(starts[row], min(ends[row], blocked[0][row])),
                      (max(starts[row], blocked[1][row]), ends[row])]
        for start, end in pieces:
            if end < start - 1e-9:
                continue
            if disc.whole:
                runs.append((row, start, end))
            else:
                runs.extend((row,) + piece for piece in
                            _sector_pieces(disc, ys[row], start, end, width, height))
    return runs


def _sector_pieces(disc, y, start, end, width, height):
    """The parts of a run of a row whose parts stay inside the sweep."""
    step = max(min(width, height) / 4, 1e-4)
    xs = np.linspace(start, end, int(math.ceil((end - start) / step)) + 1)
    centres = np.stack([xs, np.full_like(xs, y)], axis=-1)
    along = np.broadcast_to([1.0, 0.0], centres.shape)
    inside = disc.rects_in_sector(centres, along, width, height)
    return [(xs[first], xs[last]) for first, last in _runs(inside)]


def rows(disc, width, height, spacing, lattice=False, stagger=False):
    """Straight rows across the face.

    Rows run edge to edge, each filled from one side of the face to the
    other. A lattice instead keeps every part on one grid, the columns lined
    up - staggered, each other row is shifted half a part, like bricks.
    """
    top = disc.b - disc.margin
    if top <= 0 or disc.margin >= disc.narrow:
        return _empty2() + ("",)
    pitch_x, pitch_y = _pitch(width, spacing), _pitch(height, spacing)
    if lattice:
        count = int(top // pitch_y) + 1
        numbers = np.arange(-count, count + 1)
        ys = numbers * pitch_y
    else:
        ys = span(2 * top, height, spacing) - top
        numbers = np.arange(len(ys))

    centres = []
    filled = set()
    for row, start, end in _row_runs(disc, ys, width, height):
        if lattice:
            shift = pitch_x / 2 if stagger and numbers[row] % 2 else 0.0
            first = math.ceil((start - shift) / pitch_x - 1e-9)
            last = math.floor((end - shift) / pitch_x + 1e-9)
            xs = shift + np.arange(first, last + 1) * pitch_x
        else:
            xs = start - width / 2 + span(end - start + width, width, spacing)
        if len(xs):
            filled.add(row)
            centres.append(np.stack([xs, np.full_like(xs, ys[row])], axis=-1))
    if not centres:
        return _empty2() + ("",)
    centres = np.concatenate(centres)
    along = np.broadcast_to([1.0, 0.0], centres.shape).copy()
    return centres, along, "%d rows" % len(filled)


def spokes(disc, width, height, spacing, count):
    """Lines of parts running out from the middle, each lined up along its
    spoke. They start where neighbouring spokes are far enough apart not to
    run into each other; a whole circle gets a part in the middle too."""
    outer = _polygon(disc.a, disc.b, disc.margin)
    if outer is None:
        return _empty2() + ("",)
    count = max(int(count), 1)
    step = disc.sweep / count
    angles = np.arange(count) * step + (0.0 if disc.whole else step / 2)
    directions = np.stack([np.cos(angles), np.sin(angles)], axis=-1)
    sideways = _perpendicular(directions) * (height / 2)

    # the inner end of a part clears the spoke either side of it
    reach = (height + spacing) / 2 / math.tan(step / 2) if step < math.pi else 0.0
    start = np.full(count, max(reach, 0.0) + width / 2)

    low0, high0, in0 = _line_range(outer, sideways, directions)
    low1, high1, in1 = _line_range(outer, -sideways, directions)
    start = np.maximum(start, np.maximum(low0, low1) + width / 2)
    end = np.minimum(high0, high1) - width / 2
    valid = in0 & in1

    if disc.holed:
        hole = _polygon(disc.a, disc.b, disc.depth - disc.margin)
        if hole is not None:
            for offset in (sideways, -sideways, np.zeros_like(sideways)):
                _, hole_high, crossed = _line_range(hole, offset, directions)
                start = np.where(crossed, np.maximum(start, hole_high + width / 2), start)

    centres, along = [], []
    for spoke in np.flatnonzero(valid & (end >= start - 1e-9)):
        radii = start[spoke] - width / 2 + span(end[spoke] - start[spoke] + width, width, spacing)
        centres.append(radii[:, None] * directions[spoke])
        along.append(np.broadcast_to(directions[spoke], (len(radii), 2)))

    # the empty middle a whole circle's spokes leave
    if disc.whole and not disc.holed and disc.margin < disc.narrow:
        if count > 2 and start.min() - width / 2 > 0.25 * min(width, height):
            centres.append(np.zeros((1, 2)))
            along.append(np.array([[1.0, 0.0]]))
    if not centres:
        return _empty2() + ("",)
    return np.concatenate(centres), np.concatenate(along), "%d spokes" % count


def _centre_part(disc, width, height):
    """One part at the very middle, along the long axis - none with a hole."""
    if disc.holed or disc.margin >= disc.narrow:
        return _empty2()
    centres = np.zeros((1, 2))
    along = np.array([[1.0, 0.0]]) if disc.a >= disc.b else np.array([[0.0, 1.0]])
    keep = disc.rects_in_sector(centres, along, width, height)
    return centres[keep], along[keep]


def _offset_points(a, b, t, depth):
    """The points `depth` in from the outline along the normals at `t`, held
    back where they would cross the long axis."""
    cos, sin = np.cos(t), np.sin(t)
    outward = unit(np.stack([b * cos, a * sin], axis=-1))
    reach = min(a, b) * np.hypot(b * cos, a * sin) / max(a, b)
    depth = np.minimum(depth, reach)
    return np.stack([a * cos, b * sin], axis=-1) - depth[:, None] * outward


def spiral(disc, width, height, spacing, arms=1, density=0.0):
    """Spiral arms winding out from a part in the middle to the outline,
    each part lined up along its arm.

    The arms keep one part height (and the spacing) apart all the way out,
    the way the rings do - on an ellipse too, since they are wound by depth
    in from the outline. `density` packs the parts along the tight inner
    turns closer, as it does a ring's.
    """
    arms = max(int(arms), 1)
    pitch_x, pitch_y = _pitch(width, spacing), _pitch(height, spacing)
    # distances out from the middle, measured as depth in from the outline
    outermost = disc.narrow - (disc.margin + height / 2)
    if disc.holed:
        innermost = disc.narrow - (disc.depth - disc.margin - height / 2)
    else:
        # a part clear of the middle one, and of the other arms' starts
        innermost = max(width, height) / 2 + height / 2 + max(spacing, 0.0)
        if arms > 1:
            innermost = max(innermost, pitch_x / (2 * math.sin(math.pi / arms)))
    centres, along = [], []
    middle = _centre_part(disc, width, height)
    if len(middle[0]):
        centres.append(middle[0])
        along.append(middle[1])

    # how far out an arm gets each turn, so neighbouring turns are a row apart
    growth = arms * pitch_y / FULL_TURN
    if outermost > innermost:
        turn_start, turn_end = innermost / growth, outermost / growth
        step = min(width / (4 * disc.wide), 0.05)
        samples = min(int(math.ceil((turn_end - turn_start) / step)) + 1, 200000 // arms)
        turn = np.linspace(turn_start, turn_end, max(samples, 2))
        out = growth * turn
        for arm in range(arms):
            points = _offset_points(disc.a, disc.b, turn + FULL_TURN * arm / arms,
                                    disc.narrow - out)
            steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
            # length counted by a line further out, for Centre Density
            middle_out = (out[1:] + out[:-1]) / 2
            counted = steps * (1 + density * height / 2 / np.maximum(middle_out, 1e-6))
            travelled = np.concatenate([[0.0], np.cumsum(steps)])
            counted = np.concatenate([[0.0], np.cumsum(counted)])
            marks = np.arange(0.0, counted[-1] + 1e-9, pitch_x)
            points, directions = _sample(points, False, np.interp(marks, counted, travelled))
            keep = disc.rects_in_sector(points, directions, width, height)
            centres.append(points[keep])
            along.append(directions[keep])
    if not centres:
        return _empty2() + ("",)
    return np.concatenate(centres), np.concatenate(along), (
        "%d arms" % arms if arms > 1 else "1 arm"
    )


def sunflower(disc, width, height, spacing, density=0.0):
    """Parts along a golden spiral from a part in the middle - an even,
    organic spread - each turned to follow the outline. `density` gathers
    more of them into the middle, the outer ones staying as far apart."""
    reach = max(width, height) / 2
    a = disc.a - disc.margin - reach
    b = disc.b - disc.margin - reach
    if a <= 0 or b <= 0:
        return _empty2() + ("",)
    inner = 0.0
    if disc.holed:
        hole = disc.narrow - (disc.depth - disc.margin)
        inner = min(max(hole + reach, 0.0) / min(a, b), 1.0)
    fraction = disc.sweep / FULL_TURN
    area = (
        fraction * math.pi
        * max(disc.a - disc.margin, 0.0) * max(disc.b - disc.margin, 0.0)
        * (1 - (disc.narrow - disc.depth) ** 2 / disc.narrow ** 2 if disc.holed else 1.0)
    )
    count = int(area * (1 + density) / (_pitch(width, spacing) * _pitch(height, spacing)))
    if count < 1 or inner >= 1.0:
        return _empty2() + ("",)

    # a power above a half crowds them in towards the middle; the first one
    # is at the middle itself when there is no hole
    power = 0.5 * (1 + density)
    index = np.arange(count)
    radius = (inner ** (1 / power) + (1 - inner ** (1 / power)) * index / count) ** power
    angle = np.mod(index * GOLDEN_ANGLE, FULL_TURN) * fraction
    cos, sin = np.cos(angle), np.sin(angle)
    centres = np.stack([a * radius * cos, b * radius * sin], axis=-1)
    along = unit(np.stack([-a * sin, b * cos], axis=-1))
    if not disc.holed:
        along[0] = [1.0, 0.0] if disc.a >= disc.b else [0.0, 1.0]
    keep = disc.rects_in_sector(centres, along, width, height)
    return centres[keep], along[keep], ""


# Lining the outline ---
def _line_curve(disc, curve, width, spacing, facing):
    """Parts laid end to end along an outline: all the way round a whole
    circle, from one straight edge to the other on a sweep.

    Returns:
        (centres, directions along it, directions away from the face)
    """
    if len(curve) < 3:
        return _empty2() + (np.zeros((0, 2)),)
    if disc.whole:
        length = _length(curve, True)
        count = _loop_count(length, width, spacing)
        centres, along = _sample(curve, True, np.arange(count) * length / count)
    else:
        inside = np.flatnonzero(disc.in_sector(curve))
        if not len(inside):
            return _empty2() + (np.zeros((0, 2)),)
        run = curve[inside[0]:inside[-1] + 1]
        centres, along = _sample(run, False, span(_length(run, False), width, spacing))
    return centres, along, -_perpendicular(along) * facing


def rim(disc, width, spacing, offset=0.0):
    """Parts lining the circle's outline - and the hole's, and a sweep's
    straight edges - `offset` out from the face.

    Returns:
        (centres, directions along the line, directions away from the face)
    """
    pieces = [_line_curve(disc, level_curve(disc.a, disc.b, -offset), width, spacing, 1.0)]
    hole = None
    if disc.holed:
        hole = level_curve(disc.a, disc.b, disc.depth + offset)
        pieces.append(_line_curve(disc, hole, width, spacing, -1.0))

    if not disc.whole:
        outer = _polygon(disc.a, disc.b, -offset)
        inner = _polygon(disc.a, disc.b, disc.depth + offset) if disc.holed else None
        for ray, side in zip(disc.rays, (-1.0, 1.0)):
            origin = np.zeros((1, 2))
            end = _line_range(outer, origin, ray)[1][0] if outer is not None else 0.0
            start = 0.0
            if inner is not None:
                _, hole_end, crossed = _line_range(inner, origin, ray)
                start = hole_end[0] if crossed[0] else 0.0
            if end <= start:
                continue
            away = _perpendicular(ray) * side
            radii = start + span(end - start, width, spacing)
            centres = radii[:, None] * ray + away * offset
            pieces.append((
                centres,
                np.broadcast_to(ray, centres.shape).copy(),
                np.broadcast_to(away, centres.shape).copy(),
            ))
    return tuple(np.concatenate([piece[i] for piece in pieces]) for i in range(3))


# Frames ---
def _flat_frames(centres, along):
    """Parts lying flat on the circle's plane."""
    count = len(centres)
    centres3 = np.column_stack([centres, np.zeros(count)])
    along3 = np.column_stack([along, np.zeros(count)])
    normals = np.broadcast_to(_Z, (count, 3)).copy()
    return centres3, normals, along3, np.cross(normals, along3)


def _wall_frames(centres, away, height):
    """Parts standing on the plane, facing away from the face."""
    count = len(centres)
    centres3 = np.column_stack([centres, np.full(count, height / 2)])
    normals = np.column_stack([away, np.zeros(count)])
    along = np.cross(_Z, normals)
    return centres3, normals, along, np.broadcast_to(_Z, (count, 3)).copy()


def estimate(disc, topology, width, height, spacing, faces_on, rim_on, spoke_count,
             density=0.0):
    """Roughly how many parts a layout needs, to refuse a huge one before
    building it."""
    pitch_x, pitch_y = _pitch(width, spacing), _pitch(height, spacing)
    fraction = disc.sweep / FULL_TURN
    a, b = max(disc.a - disc.margin, 0.0), max(disc.b - disc.margin, 0.0)
    total = 0.0
    if faces_on:
        if topology == SPOKES:
            total += spoke_count * (disc.wide / pitch_x + 1)
        else:
            total += fraction * math.pi * a * b / (pitch_x * pitch_y)
            if topology in DENSITY_TOPOLOGIES:
                total *= 1 + density
    if rim_on:
        perimeter = math.pi * (3 * (disc.a + disc.b)
                               - math.sqrt((3 * disc.a + disc.b) * (disc.a + 3 * disc.b)))
        total += perimeter * fraction * (2 if disc.holed else 1) / pitch_x
    return total


def fill(disc, topology, width, height, spacing=0.0, faces_on=True, rim_on=False,
         rim_style=FLAT, rim_offset=0.0, spoke_count=12, stagger=False, arms=1,
         density=0.0):
    """Every part's frame for a circle.

    Args:
        width, height: the room a part takes along and across its line.

    Returns:
        (centres, normals, along, up, a word on the face's layout)
    """
    groups = []
    detail = ""
    if faces_on:
        if topology == ROWS:
            centres, along, detail = rows(disc, width, height, spacing)
        elif topology == GRID:
            centres, along, detail = rows(disc, width, height, spacing, lattice=True,
                                          stagger=stagger)
        elif topology == SPOKES:
            centres, along, detail = spokes(disc, width, height, spacing, spoke_count)
        elif topology == SPIRAL:
            centres, along, detail = spiral(disc, width, height, spacing, arms, density)
        elif topology == SUNFLOWER:
            centres, along, detail = sunflower(disc, width, height, spacing, density)
        else:
            centres, along, detail = rings(disc, width, height, spacing, stagger, density)
        groups.append(_flat_frames(centres, along))
    if rim_on:
        centres, along, away = rim(disc, width, spacing, rim_offset)
        if rim_style == WALL:
            groups.append(_wall_frames(centres, away, height))
        else:
            groups.append(_flat_frames(centres, along))
    if not groups:
        empty = np.zeros((0, 3))
        return empty, empty, empty, empty, detail
    return tuple(np.concatenate([group[i] for group in groups]) for i in range(4)) + (detail,)
