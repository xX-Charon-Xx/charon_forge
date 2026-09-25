"""Where the copies of a Forge sphere go, for each way of building one.

Pure numpy, no Blender: every topology comes down to a unit normal per copy
plus the two directions its part's sides line up with (`along` and `up`,
both on the surface). place() turns those into positions and rotations.
Kept apart from objects/sphere.py so it can be run and checked outside Blender.
"""

import math

import numpy as np

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


def _unit(vectors):
    lengths = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.where(lengths > 0, lengths, 1)


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


def in_range(normals, bottom, top, sweep):
    """Which points fall between the latitudes and inside the sweep."""
    latitudes = np.arcsin(np.clip(normals[:, 2], -1.0, 1.0))
    keep = (latitudes >= bottom - 1e-6) & (latitudes <= top + 1e-6)
    if sweep < FULL_TURN - 1e-4:
        longitudes = np.arctan2(normals[:, 1], normals[:, 0]) % FULL_TURN
        keep &= longitudes <= sweep + 1e-6
    return keep


# Rings of latitude ---
def latitude_plan(bottom, top, rings):
    """(latitudes, step) for rings spread from bottom to top, both ends
    included - a sphere's rings run pole to pole."""
    if rings <= 1 or top - bottom < 1e-6:
        return np.array([(bottom + top) / 2]), 0.0
    step = (top - bottom) / (rings - 1)
    return bottom + np.arange(rings) * step, step


def ring_count(equator, latitude, step, pole_density):
    """Copies on the ring at a latitude.

    Flat copies are laid along the ring's wider edge - the one nearer the
    equator - so that is the circumference they have to cover; rounding up
    means a ring is never short. A ring at a pole is one copy.
    """
    if abs(latitude) > POLE:
        return 1
    edge = max(abs(latitude) - abs(step) / 2, 0.0)
    extra = 1 + pole_density * abs(math.sin(latitude))
    return max(1, math.ceil(equator * math.cos(edge) * extra - 1e-4))


def rings(bottom, top, sweep, ring_total, equator, pole_density, stagger):
    latitudes, step = latitude_plan(bottom, top, ring_total)
    shift = 0.5 if stagger and sweep >= FULL_TURN - 1e-4 else 0.0
    all_latitudes, all_longitudes = [], []
    for ring, latitude in enumerate(latitudes):
        count = ring_count(equator, latitude, step, pole_density)
        index = np.arange(count)
        all_longitudes.append((index + 0.5 + (ring % 2) * shift) * sweep / count)
        all_latitudes.append(np.full(count, latitude))
    return lat_lon_frame(np.concatenate(all_latitudes), np.concatenate(all_longitudes))


# One ring turned about the axis ---
def meridians(bottom, top, sweep, along, meridian_total):
    """The same number of copies on every meridian - they close in on each
    other towards the poles, where only one copy is kept."""
    latitudes, _ = latitude_plan(bottom, top, along)
    longitudes = (np.arange(meridian_total) + 0.5) * sweep / meridian_total
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


def geodesic(bottom, top, sweep, frequency):
    normals = geodesic_points(frequency)
    return frame_from_normals(normals[in_range(normals, bottom, top, sweep)])


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


def cube(bottom, top, sweep, grid):
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

    keep = in_range(normals, bottom, top, sweep)
    normals, alongs = normals[keep], alongs[keep]
    return normals, alongs, np.cross(normals, alongs)


# Spiral ---
def spiral(bottom, top, sweep, count):
    """`count` points spread over the whole sphere along a golden-angle
    spiral, of which those in range are kept."""
    index = np.arange(count)
    z = 1 - 2 * (index + 0.5) / count
    radius = np.sqrt(np.clip(1 - z * z, 0.0, 1.0))
    angle = index * GOLDEN_ANGLE
    normals = np.stack([radius * np.cos(angle), radius * np.sin(angle), z], axis=-1)
    return frame_from_normals(normals[in_range(normals, bottom, top, sweep)])


# Placing ---
def place(normals, along, up, radius, turn, centre, scale):
    """Positions and rotations for the copies.

    Args:
        turn (3x3): the part's rotation into the surface frame (x along,
            y up, z out), its local rotation included.
        centre (3): the part's centre in that frame, kept on the surface.
        scale (float): every copy's scale.

    Returns:
        (N x 3, N x 3 x 3): where each copy's origin goes, and its rotation.
    """
    frames = np.stack([along, up, normals], axis=-1)
    rotations = frames @ np.asarray(turn, dtype=np.float64)
    offsets = frames @ np.asarray(centre, dtype=np.float64)
    return normals * radius - offsets * scale, rotations


def to_quaternions(matrices):
    """(w, x, y, z) for each rotation matrix - Shepperd's method, picking the
    stable branch per matrix."""
    m = matrices
    m00, m01, m02 = m[:, 0, 0], m[:, 0, 1], m[:, 0, 2]
    m10, m11, m12 = m[:, 1, 0], m[:, 1, 1], m[:, 1, 2]
    m20, m21, m22 = m[:, 2, 0], m[:, 2, 1], m[:, 2, 2]
    trace = m00 + m11 + m22

    def root(value):
        return np.sqrt(np.clip(value, 1e-12, None)) * 2

    s0 = root(trace + 1)
    s1 = root(1 + m00 - m11 - m22)
    s2 = root(1 + m11 - m00 - m22)
    s3 = root(1 + m22 - m00 - m11)
    candidates = np.stack([
        np.stack([s0 / 4, (m21 - m12) / s0, (m02 - m20) / s0, (m10 - m01) / s0], -1),
        np.stack([(m21 - m12) / s1, s1 / 4, (m01 + m10) / s1, (m02 + m20) / s1], -1),
        np.stack([(m02 - m20) / s2, (m01 + m10) / s2, s2 / 4, (m12 + m21) / s2], -1),
        np.stack([(m10 - m01) / s3, (m02 + m20) / s3, (m12 + m21) / s3, s3 / 4], -1),
    ])
    branch = np.where(
        trace > 0, 0,
        np.where((m00 > m11) & (m00 > m22), 1, np.where(m11 > m22, 2, 3)),
    )
    return candidates[branch, np.arange(len(m))]
