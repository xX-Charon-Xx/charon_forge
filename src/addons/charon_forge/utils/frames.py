"""Placing parts on surface frames: a point with `along` and `up` on the surface
and `normal` out of it. Pure numpy, no Blender."""

import math

import numpy as np

FULL_TURN = 2 * math.pi


def arc(start, end):
    """(start, sweep) going anticlockwise from `start` to `end`, wrapping past 360°.
    The same start and end make a full turn."""
    start = start % FULL_TURN
    sweep = (end - start) % FULL_TURN
    return start, (FULL_TURN if sweep < 1e-6 else sweep)



def unit(vectors):
    lengths = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.where(lengths > 0, lengths, 1)


def stretch(centres, normals, along, axes):
    """Carry frames onto their surface stretched by `axes`, keeping parts flat on it.
    Returns (centres, normals, along, up)."""
    axes = np.asarray(axes, dtype=np.float64)
    out = unit(normals / axes)
    stretched = along * axes
    along = unit(stretched - out * (stretched * out).sum(axis=1, keepdims=True))
    return centres * axes, out, along, np.cross(out, along)


def place(centres, normals, along, up, turn, centre, scale):
    """Origins and rotations for parts laid on frames; `turn` rotates a part into a
    frame (x along, y up, z out) and `centre` is put on the frame's point."""
    frames = np.stack([along, up, normals], axis=-1)
    rotations = frames @ np.asarray(turn, dtype=np.float64)
    offsets = frames @ np.asarray(centre, dtype=np.float64)
    scale = np.asarray(scale, dtype=np.float64)
    if scale.ndim:
        scale = scale[:, None]
    return centres - offsets * scale, rotations


def from_quaternions(quaternions):
    """The rotation matrix of each (w, x, y, z)."""
    w, x, y, z = unit(np.asarray(quaternions, dtype=np.float64)).T
    return np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
        np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
        np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1),
    ], axis=1)


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
