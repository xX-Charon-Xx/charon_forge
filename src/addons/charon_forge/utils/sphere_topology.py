"""Where the copies of a Forge sphere go, for each way of building one.

Pure numpy, no Blender: every topology comes down to a unit normal per copy
plus the two directions its part's sides line up with (`along` and `up`,
both on the surface). place() turns those into positions and rotations.
Kept apart from objects/sphere.py so it can be run and checked outside
Blender.
"""

import math

import numpy as np

from . import frames
from .frames import arc  # noqa: F401 - the sphere's sweep
from .frames import unit as _unit

RINGS = "RINGS"
MERIDIANS = "MERIDIANS"
GEODESIC = "GEODESIC"
CUBE = "CUBE"
SPIRAL = "SPIRAL"

FULL_TURN = 2 * math.pi
POLE = math.pi / 2 - 1e-4
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))
# edge of an icosahedron whose corners are on the unit sphere
ICOSAHEDRON_EDGE = 4 / math.sqrt(10 + 2 * math.sqrt(5))


def lat_lon_frame(latitudes, longitudes):
    """(normal, east, north) at each latitude and longitude."""
    cos_lat, sin_lat = np.cos(latitudes), np.sin(latitudes)
    cos_lon, sin_lon = np.cos(longitudes), np.sin(longitudes)
    normal = np.stack([cos_lat * cos_lon, cos_lat * sin_lon, sin_lat], axis=-1)
    east = np.stack([-sin_lon, cos_lon, np.zeros_like(cos_lon)], axis=-1)
    return normal, east, np.cross(normal, east)


def frame_from_normals(normals):
    """(normal, east, north) for points given by their normals."""
    latitudes = np.arcsin(np.clip(normals[:, 2], -1.0, 1.0))
    longitudes = np.arctan2(normals[:, 1], normals[:, 0])
    _, east, _ = lat_lon_frame(latitudes, longitudes)
    return normals, east, np.cross(normals, east)


def in_range(normals, bottom, top, start, sweep):
    """Which points fall between the latitudes and inside the sweep, which
    runs anticlockwise from the `start` longitude."""
    latitudes = np.arcsin(np.clip(normals[:, 2], -1.0, 1.0))
    keep = (latitudes >= bottom - 1e-6) & (latitudes <= top + 1e-6)
    if sweep < FULL_TURN - 1e-4:
        longitudes = (np.arctan2(normals[:, 1], normals[:, 0]) - start) % FULL_TURN
        # just short of a full turn is back at the start
        keep &= (longitudes <= sweep + 1e-6) | (longitudes >= FULL_TURN - 1e-6)
    return keep


# Rings of latitude ---
def latitude_plan(bottom, top, rings):
    """(latitudes, step) for rings spread from bottom to top, both ends
    included - a sphere's rings run pole to pole."""
    if rings <= 1 or top - bottom < 1e-6:
        return np.array([(bottom + top) / 2]), 0.0
    step = (top - bottom) / (rings - 1)
    return bottom + np.arange(rings) * step, step


# latitudes the pole weighting is worked out at, pole to pole
_WEIGHT_TABLE = np.linspace(-math.pi / 2, math.pi / 2, 4097)


def _pole_weight(latitudes, pole_density, pole_part_size=0.0):
    """How far each latitude is from the equator, counting every radian as
    (1 + pole_density |sin|) / pole_scale of them - so rings spaced evenly in
    it bunch up towards the poles, both for Pole Density and to keep the
    smaller copies Pole Part Size makes there a copy apart, with no gaps
    between their rings."""
    sine = np.abs(np.sin(_WEIGHT_TABLE))
    rate = (1 + pole_density * sine) / pole_scale(sine, pole_part_size)
    # summed out from the equator, in the middle of the table
    steps = (rate[1:] + rate[:-1]) / 2 * np.diff(_WEIGHT_TABLE)
    weights = np.concatenate([[0.0], np.cumsum(steps)])
    weights -= weights[len(weights) // 2]
    return np.interp(latitudes, _WEIGHT_TABLE, weights)


def weighted_span(bottom, top, pole_density, pole_part_size=0.0):
    """The span from bottom to top as the rings count it - wider than
    top - bottom by the rings Pole Density and Pole Part Size add towards
    the poles."""
    weights = _pole_weight([bottom, top], pole_density, pole_part_size)
    return float(weights[1] - weights[0])


def bunched_latitudes(bottom, top, rings, pole_density, pole_part_size=0.0):
    """(latitudes, steps) for rings from bottom to top, closer together
    towards the poles the higher pole_density and pole_part_size are; each
    step is the gap between the ring and its neighbours."""
    latitudes, step = latitude_plan(bottom, top, rings)
    if len(latitudes) < 2 or (pole_density <= 0.0 and pole_part_size <= 0.0):
        return latitudes, np.full(len(latitudes), step)
    # evenly spaced in the weighted span, turned back into latitudes
    table = np.linspace(bottom, top, 2048)
    weights = _pole_weight(table, pole_density, pole_part_size)
    latitudes = np.interp(np.linspace(weights[0], weights[-1], rings), weights, table)
    return latitudes, np.gradient(latitudes)


def pole_scale(heights, pole_part_size):
    """How big a copy is against the rest - 1 at the equator, shrinking by
    `pole_part_size` towards the poles - for copies at `heights`, the z of
    their unit normals."""
    return 1.0 - pole_part_size * np.abs(heights)


def pole_crowding(pole_part_size):
    """How many times as many copies a whole sphere takes once Pole Part
    Size shrinks them - its area counted by 1 / pole_scale^2, the room each
    smaller copy takes, against its plain area."""
    return 1.0 / (1.0 - pole_part_size)


def crowd_to_poles(normals, pole_part_size):
    """Points spread evenly over the sphere moved up or down towards the
    poles, each keeping its longitude, so that they end up 1 / pole_scale^2
    as crowded - the copies Pole Part Size shrinks there as close together
    as the full-size ones at the equator. It leaves them pole_crowding times
    as spread out at the equator, which the counts make up for.

    Evenly spread points are even in z, so each z moves to where as much of
    the sphere's area counted by 1 / pole_scale^2 is below it:
    z' / (1 - p |z'|) = z / (1 - p).
    """
    if pole_part_size <= 0.0 or not len(normals):
        return normals
    heights = normals[:, 2]
    counted = heights * pole_crowding(pole_part_size)
    moved = counted / (1 + pole_part_size * np.abs(counted))
    # round the axis, the same longitude at the new height
    before = np.sqrt(np.clip(1 - heights * heights, 0.0, 1.0))
    after = np.sqrt(np.clip(1 - moved * moved, 0.0, 1.0))
    ratio = np.where(before > 1e-9, after / np.maximum(before, 1e-9), 0.0)
    return np.stack([normals[:, 0] * ratio, normals[:, 1] * ratio, moved], axis=-1)


def ring_count(equator, latitude, step, pole_density, pole_part_size=0.0):
    """Copies on the ring at a latitude.

    Flat copies are laid along the ring's wider edge - the one nearer the
    equator - so that is the circumference they have to cover; rounding up
    means a ring is never short. Copies made smaller towards the poles take
    more to go round. A ring at a pole is one copy.
    """
    if abs(latitude) > POLE:
        return 1
    edge = max(abs(latitude) - abs(step) / 2, 0.0)
    extra = (1 + pole_density * abs(math.sin(latitude))) / pole_scale(
        math.sin(latitude), pole_part_size)
    return max(1, math.ceil(equator * math.cos(edge) * extra - 1e-4))


def rings(bottom, top, start, sweep, ring_total, equator, pole_density, stagger,
          pole_part_size=0.0):
    latitudes, steps = bunched_latitudes(bottom, top, ring_total, pole_density,
                                         pole_part_size)
    shift = 0.5 if stagger and sweep >= FULL_TURN - 1e-4 else 0.0
    all_latitudes, all_longitudes = [], []
    for ring, (latitude, step) in enumerate(zip(latitudes, steps)):
        count = ring_count(equator, latitude, step, pole_density, pole_part_size)
        index = np.arange(count)
        all_longitudes.append(start + (index + 0.5 + (ring % 2) * shift) * sweep / count)
        all_latitudes.append(np.full(count, latitude))
    return lat_lon_frame(np.concatenate(all_latitudes), np.concatenate(all_longitudes))


# One ring turned about the axis ---
def meridians(bottom, top, start, sweep, along, meridian_total, pole_part_size=0.0):
    """The same number of copies on every meridian - they close in on each
    other towards the poles, where only one copy is kept. The rings of them
    bunch up towards the poles to meet the copies Pole Part Size shrinks."""
    latitudes, _ = bunched_latitudes(bottom, top, along, 0.0, pole_part_size)
    longitudes = start + (np.arange(meridian_total) + 0.5) * sweep / meridian_total
    all_latitudes, all_longitudes = [], []
    for latitude in latitudes:
        ring_longitudes = longitudes[:1] if abs(latitude) > POLE else longitudes
        all_longitudes.append(ring_longitudes)
        all_latitudes.append(np.full(len(ring_longitudes), latitude))
    return lat_lon_frame(np.concatenate(all_latitudes), np.concatenate(all_longitudes))


# Geodesic ---
def _icosahedron():
    """Corners and faces of an icosahedron with a corner at each pole, so a
    dome cut at the equator comes out symmetrical."""
    height, radius = 1 / math.sqrt(5), 2 / math.sqrt(5)
    corners = [(0.0, 0.0, 1.0)]
    corners += [
        (radius * math.cos(k * FULL_TURN / 5), radius * math.sin(k * FULL_TURN / 5), height)
        for k in range(5)
    ]
    corners += [
        (radius * math.cos((k + 0.5) * FULL_TURN / 5),
         radius * math.sin((k + 0.5) * FULL_TURN / 5), -height)
        for k in range(5)
    ]
    corners.append((0.0, 0.0, -1.0))

    faces = []
    for k in range(5):
        upper, upper_next = 1 + k, 1 + (k + 1) % 5
        lower, lower_next = 6 + k, 6 + (k + 1) % 5
        faces += [
            (0, upper, upper_next),
            (upper, lower, upper_next),
            (upper_next, lower, lower_next),
            (11, lower_next, lower),
        ]
    return np.array(corners), np.array(faces)


def geodesic_points(frequency):
    """The corners of an icosahedron with every edge cut into `frequency`
    pieces, on the unit sphere - 10 f^2 + 2 of them."""
    corners, faces = _icosahedron()
    steps = np.array([(i, j) for i in range(frequency + 1) for j in range(frequency + 1 - i)])
    a, b, c = corners[faces[:, 0]], corners[faces[:, 1]], corners[faces[:, 2]]
    weights_b = steps[:, 0][None, :, None] / frequency
    weights_c = steps[:, 1][None, :, None] / frequency
    points = a[:, None] + (b - a)[:, None] * weights_b + (c - a)[:, None] * weights_c
    points = _unit(points.reshape(-1, 3))
    # neighbouring faces share their edge points
    _, first = np.unique(np.round(points, 6), axis=0, return_index=True)
    return points[np.sort(first)]


def geodesic(bottom, top, start, sweep, frequency, pole_part_size=0.0):
    normals = crowd_to_poles(geodesic_points(frequency), pole_part_size)
    return frame_from_normals(normals[in_range(normals, bottom, top, start, sweep)])


# Cube ---
_CUBE_FACES = (
    # normal, along, up - along runs east round the sides, like the rings
    ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
    ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
    ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    ((0, 0, -1), (1, 0, 0), (0, -1, 0)),
)


def cube(bottom, top, start, sweep, grid, pole_part_size=0.0):
    """A grid on each face of a cube, pushed out onto the sphere. Spaced by
    equal angles rather than equally on the cube, so the copies near a
    face's edges are not stretched apart."""
    spots = np.tan(((np.arange(grid) + 0.5) / grid * 2 - 1) * math.pi / 4)
    u, v = np.meshgrid(spots, spots, indexing="ij")
    u, v = u.ravel(), v.ravel()

    normals, alongs = [], []
    for normal, along, up in _CUBE_FACES:
        normal, along, up = np.array(normal, float), np.array(along, float), np.array(up, float)
        points = _unit(normal[None] + u[:, None] * along[None] + v[:, None] * up[None])
        # the face's own direction, laid onto the sphere at each point
        tangent = along[None] - points * (points @ along)[:, None]
        normals.append(points)
        alongs.append(_unit(tangent))
    normals, alongs = np.concatenate(normals), np.concatenate(alongs)
    if pole_part_size > 0.0:
        # the face's direction laid onto the sphere again where they moved to
        normals = crowd_to_poles(normals, pole_part_size)
        alongs = _unit(alongs - normals * (normals * alongs).sum(axis=1, keepdims=True))

    keep = in_range(normals, bottom, top, start, sweep)
    normals, alongs = normals[keep], alongs[keep]
    return normals, alongs, np.cross(normals, alongs)


# Spiral ---
def spiral(bottom, top, start, sweep, count, pole_part_size=0.0):
    """`count` points spread over the whole sphere along a golden-angle
    spiral, of which those in range are kept."""
    index = np.arange(count)
    z = 1 - 2 * (index + 0.5) / count
    radius = np.sqrt(np.clip(1 - z * z, 0.0, 1.0))
    angle = index * GOLDEN_ANGLE
    normals = np.stack([radius * np.cos(angle), radius * np.sin(angle), z], axis=-1)
    normals = crowd_to_poles(normals, pole_part_size)
    return frame_from_normals(normals[in_range(normals, bottom, top, start, sweep)])


# Placing ---
def ellipsoid(normals, along, up, radius, axes=(1.0, 1.0, 1.0)):
    """The frames on a sphere of `radius`, stretched by `axes` into an
    ellipsoid: each point moves with the stretch, its sides turn with the
    surface under it (directions along a surface stretch like it, the one out
    of it by the inverse) so a copy still lies flat on it.

    Returns:
        (centres, normals, along, up)
    """
    axes = np.asarray(axes, dtype=np.float64)
    centres = normals * radius * axes
    if np.allclose(axes, 1.0):
        return centres, normals, along, up
    out = _unit(normals / axes)
    stretched = along * axes
    along = _unit(stretched - out * (stretched * out).sum(axis=1, keepdims=True))
    return centres, out, along, np.cross(out, along)


def place(normals, along, up, radius, turn, centre, scale, axes=(1.0, 1.0, 1.0)):
    """Positions and rotations for copies on a sphere of `radius`, stretched
    by `axes` - see frames.place."""
    return frames.place(*ellipsoid(normals, along, up, radius, axes), turn, centre, scale)
