"""Shapes for The Forge, and where parts go on them.

A shape is corners, and faces as loops of corner indices, each face flat
and convex and counter-clockwise seen from outside. Some styles are the
convex hull of corners placed for them (Even, Pyramid, Prism...); the rest
are built face by face (a donut, a cylinder, a cuboid...), so need not be
convex overall. Either way it is sized and stretched, and parts can then
fill its faces, line its edges and sit on its corners, never reaching past
a face's boundary or an edge's ends.

Pure numpy, no Blender.
"""

import collections
import functools
import itertools
import math

import numpy as np

from .frames import stretch as frames_stretch
from .frames import unit

EVEN = "EVEN"
PYRAMID = "PYRAMID"
BIPYRAMID = "BIPYRAMID"
PRISM = "PRISM"
ANTIPRISM = "ANTIPRISM"
TORUS = "TORUS"
CYLINDER = "CYLINDER"
CONE = "CONE"
CAPSULE = "CAPSULE"
STAR = "STAR"
CUBOID = "CUBOID"

FULL_TURN = 2 * math.pi

# built from a corner count, as a convex hull
HULL_STYLES = (EVEN, PYRAMID, BIPYRAMID, PRISM, ANTIPRISM)
# spun round the Z axis, so they can sweep less than a full turn
SWEPT_STYLES = (TORUS, CYLINDER, CONE, CAPSULE)

MIN_VERTICES = {EVEN: 4, PYRAMID: 4, BIPYRAMID: 5, PRISM: 6, ANTIPRISM: 6}
MAX_VERTICES = 100
# styles made of two matching rings, so always an even count of corners
PAIRED = (PRISM, ANTIPRISM)


def snap_vertices(style, count, previous):
    """The nearest corner count the style can have, stepping on in the
    direction the count was moving so an odd count typed into a prism
    doesn't just bounce back."""
    count = min(max(count, MIN_VERTICES.get(style, 4)), MAX_VERTICES)
    if style in PAIRED and count % 2:
        count += 1 if count > previous else -1
        count = min(max(count, MIN_VERTICES[style]), MAX_VERTICES)
    return count


# Corners ---
def _spiral(count):
    index = np.arange(count)
    z = 1 - 2 * (index + 0.5) / count
    radius = np.sqrt(np.clip(1 - z * z, 0.0, 1.0))
    angle = index * math.pi * (3 - math.sqrt(5))
    return np.stack([radius * np.cos(angle), radius * np.sin(angle), z], axis=-1)


def even_points(count, iterations=600):
    """`count` points on the unit sphere pushed as far from each other as
    they will go - charges repelling (the Thomson problem). For 4, 6 and 12
    that is the tetrahedron, octahedron and icosahedron, all edges equal,
    and close to equal for any other count."""
    points = _spiral(count)
    spacing = math.sqrt(4 * math.pi / count)
    for step in range(iterations):
        offsets = points[:, None, :] - points[None, :, :]
        distances = np.linalg.norm(offsets, axis=-1) + np.eye(count) * 1e9
        force = (offsets / distances[..., None] ** 3).sum(axis=1)
        # only the push along the sphere moves a point
        force -= (force * points).sum(axis=1, keepdims=True) * points
        strength = np.linalg.norm(force, axis=1).max()
        if strength < 1e-12:
            break
        move = 0.1 * spacing * (1 - step / iterations)
        points = unit(points + force / strength * move)
    return points


def _hull_edges(points):
    faces = hull_faces(points, merge=False)
    return np.array(sorted(edges_of(faces)))


def equal_edges(points, iterations=3000, rounds=6):
    """Pull every edge of the points' hull towards the same length, the way
    springs would settle - where a shape with all edges equal exists (4, 5,
    6, 7, 8, 9, 10 and 12 corners) this finds it, and for any other count it
    gets as close as the corners allow. The hull is taken again between
    rounds, in case an edge flips to the other diagonal on the way.

    Where no equal shape exists the springs can pull a corner inside the
    others; the best shape seen with every corner still on the outside is
    what comes back."""
    points = points.copy()
    best, best_spread = points.copy(), math.inf
    for _ in range(rounds + 1):
        if not np.isfinite(points).all():
            break
        edges = _hull_edges(points)
        degree = np.bincount(edges.ravel(), minlength=len(points))[:, None]
        if (degree == 0).any():
            break
        a, b = edges[:, 0], edges[:, 1]
        lengths = np.linalg.norm(points[b] - points[a], axis=1)
        spread = lengths.max() / lengths.min()
        if spread < best_spread:
            best, best_spread = points.copy(), spread
        for _ in range(iterations // rounds):
            offsets = points[b] - points[a]
            lengths = np.linalg.norm(offsets, axis=1)
            error = (lengths - lengths.mean()) / lengths
            push = offsets * (0.5 * error)[:, None]
            delta = np.zeros_like(points)
            np.add.at(delta, a, push)
            np.add.at(delta, b, -push)
            points += delta / degree
            points -= points.mean(axis=0)
    return best


def _ring(sides, height, radius=1.0, turn=0.0):
    angles = np.arange(sides) * 2 * math.pi / sides + turn
    return np.stack([
        radius * np.cos(angles), radius * np.sin(angles), np.full(sides, height)
    ], axis=-1)


def _equal_edge_height(sides):
    """How high above a unit ring a point must be for its edges to every
    ring corner to equal the ring's own edges - or None where no height
    does (six sides and up: the ring's edges are shorter than its radius)."""
    side = 2 * math.sin(math.pi / sides)
    return math.sqrt(side * side - 1) if side > 1 else None


def style_vertices(style, count):
    """The corners of a shape of a style with `count` corners (or the
    nearest count the style can have)."""
    if style == PYRAMID:
        sides = max(3, count - 1)
        height = _equal_edge_height(sides) or 1.0
        return np.vstack([_ring(sides, 0.0), [(0.0, 0.0, height)]])
    if style == BIPYRAMID:
        sides = max(3, count - 2)
        height = _equal_edge_height(sides) or 1.0
        return np.vstack([_ring(sides, 0.0), [(0.0, 0.0, height), (0.0, 0.0, -height)]])
    if style == PRISM:
        sides = max(3, count // 2)
        side = 2 * math.sin(math.pi / sides)
        return np.vstack([_ring(sides, -side / 2), _ring(sides, side / 2)])
    if style == ANTIPRISM:
        sides = max(3, count // 2)
        side = 2 * math.sin(math.pi / sides)
        step = 2 * math.sin(math.pi / (2 * sides))
        height = math.sqrt(max(side * side - step * step, 1e-6))
        return np.vstack([
            _ring(sides, -height / 2), _ring(sides, height / 2, turn=math.pi / sides)
        ])
    return equal_edges(even_points(max(4, count)))


# Faces ---
def hull_faces(points, tolerance=1e-7, merge=True):
    """The faces of the convex hull of points, each a loop of point indices
    counter-clockwise seen from outside. Coplanar triangles are merged, so a
    prism's sides come out as squares, not pairs of triangles - unless
    `merge` is off, when every face is a triangle."""
    count = len(points)
    triples = np.array(list(itertools.combinations(range(count), 3)))
    a, b, c = points[triples[:, 0]], points[triples[:, 1]], points[triples[:, 2]]
    normals = np.cross(b - a, c - a)
    lengths = np.linalg.norm(normals, axis=1)
    usable = lengths > 1e-9
    triples, a, normals = triples[usable], a[usable], normals[usable] / lengths[usable, None]
    offsets = (normals * a).sum(axis=1)

    below = np.ones(len(triples), bool)
    above = np.ones(len(triples), bool)
    for start in range(0, len(triples), 4000):
        chunk = slice(start, start + 4000)
        side = points @ normals[chunk].T - offsets[chunk]
        below[chunk] = (side <= tolerance).all(axis=0)
        above[chunk] = (side >= -tolerance).all(axis=0)

    on_hull = below | above
    normals = np.where(above[:, None] & ~below[:, None], -normals, normals)[on_hull]
    offsets = np.where(above & ~below, -offsets, offsets)[on_hull]

    planes = {}
    for index, (triple, normal, offset) in enumerate(zip(triples[on_hull], normals, offsets)):
        key = tuple(np.round(np.append(normal, offset), 4)) if merge else index
        entry = planes.setdefault(key, (normal, set()))
        entry[1].update(int(i) for i in triple)

    faces = []
    for normal, members in planes.values():
        members = np.array(sorted(members))
        middle = points[members].mean(axis=0)
        u = unit(points[members[0]] - middle)
        w = np.cross(normal, u)
        relative = points[members] - middle
        angles = np.arctan2(relative @ w, relative @ u)
        faces.append(tuple(members[np.argsort(angles)]))
    return faces


def _rotation_between(source, target):
    """The rotation turning unit vector `source` onto `target`."""
    axis = np.cross(source, target)
    sine, cosine = np.linalg.norm(axis), float(np.dot(source, target))
    if sine < 1e-9:
        if cosine > 0:
            return np.eye(3)
        # half a turn about any axis square to source
        other = np.array([1.0, 0.0, 0.0]) if abs(source[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        axis = unit(np.cross(source, other))
        return 2 * np.outer(axis, axis) - np.eye(3)
    axis = axis / sine
    cross = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + sine * cross + (1 - cosine) * cross @ cross


def face_normal(points):
    """A polygon's unit normal, by Newell's method."""
    following = np.roll(points, -1, axis=0)
    return unit(np.cross(points, following).sum(axis=0))


def face_area(points):
    return 0.5 * np.linalg.norm(np.cross(points, np.roll(points, -1, axis=0)).sum(axis=0))


def edges_of(faces):
    """{(a, b): [faces]} for every edge, a < b."""
    edges = {}
    for index, face in enumerate(faces):
        for a, b in zip(face, face[1:] + face[:1]):
            edges.setdefault((min(a, b), max(a, b)), []).append(index)
    return edges


# Meshes ---
# A shape's corners and faces, with everything about how they connect worked
# out once: faces grouped by corner count (so their frames are one array op
# per group), every edge with the faces either side of it (-1 where the shape
# is open), and every corner with the faces around it and a neighbour to line
# a corner part up with. Only `vertices` changes as a shape is sized.
#
# A shape spun round the Z axis also keeps what it was spun from -
# `revolution` is (profile, closed, sweep) - with its first `side_count`
# faces the spun side, so fill() can cover that side as one smooth surface
# rather than as its many narrow faces, none of which a part may fit on.
# `scale` is the size and stretch its vertices were given.
Mesh = collections.namedtuple(
    "Mesh",
    "vertices faces groups edges edge_faces corner_vertex corner_face corners neighbours "
    "revolution side_count scale",
    defaults=(None, 0, (1.0, 1.0, 1.0)),
)


def make_mesh(vertices, faces):
    faces = tuple(tuple(int(i) for i in face) for face in faces)
    grouped = {}
    for index, face in enumerate(faces):
        grouped.setdefault(len(face), []).append(index)
    groups = {
        size: (np.array(ids), np.array([faces[i] for i in ids]))
        for size, ids in grouped.items()
    }

    edge_map = edges_of(faces)
    edges = np.array(list(edge_map.keys()), dtype=int).reshape(-1, 2)
    edge_faces = np.array(
        [(list(sides) + [-1, -1])[:2] for sides in edge_map.values()], dtype=int
    ).reshape(-1, 2)

    corner_vertex = np.array([corner for face in faces for corner in face], dtype=int)
    corner_face = np.repeat(np.arange(len(faces)), [len(face) for face in faces])
    neighbour = {}
    for face in faces:
        for position, corner in enumerate(face):
            neighbour.setdefault(corner, face[(position + 1) % len(face)])
    corners = np.array(sorted(neighbour), dtype=int)
    neighbours = np.array([neighbour[corner] for corner in corners], dtype=int)

    vertices = np.array(vertices, dtype=np.float64)
    vertices.setflags(write=False)
    return Mesh(vertices, faces, groups, edges, edge_faces, corner_vertex, corner_face,
                corners, neighbours)


@functools.lru_cache(maxsize=64)
def unit_shape(style, count):
    """A hull style at unit size: centred, its farthest corner 1 away, and
    resting on its largest face, so it stands flat."""
    vertices = style_vertices(style, count)
    vertices = vertices - vertices.mean(axis=0)
    faces = hull_faces(vertices)

    if style == EVEN:
        base = max(faces, key=lambda face: face_area(vertices[list(face)]))
        down = _rotation_between(face_normal(vertices[list(base)]), np.array([0.0, 0.0, -1.0]))
        vertices = vertices @ down.T

    vertices = vertices / np.linalg.norm(vertices, axis=1).max()
    return make_mesh(vertices, faces)


# Built shapes ---
def _oriented(points, face, outward):
    """The face turned so it is counter-clockwise seen from `outward`."""
    normal = np.cross(points[list(face)], np.roll(points[list(face)], -1, axis=0)).sum(axis=0)
    return tuple(face) if normal @ outward >= 0 else tuple(reversed(face))


def revolve(profile, sides, sweep=FULL_TURN, closed=False, capped=True):
    """A profile of (radius, height) points spun `sweep` round the Z axis in
    `sides` steps - faces counter-clockwise seen from outside. Returns the
    corners, the faces (the spun side first) and the Mesh `revolution`,
    with the side's face count.

    An open profile runs bottom to top, and a point on the axis (radius 0)
    becomes one corner. A closed profile (a donut's tube) loops back to its
    start. `capped` closes the ends: a flat ring or disc on an open profile,
    and the cut faces of anything swept less than a full turn.
    """
    profile = [(max(float(r), 0.0), float(z)) for r, z in profile]
    full = sweep >= FULL_TURN - 1e-6
    columns = sides if full else sides + 1
    angles = np.arange(columns) * (sweep / sides)

    vertices, ids = [], {}

    def corner(k, j):
        radius, height = profile[k]
        key = (k, None) if radius < 1e-9 else (k, j)
        if key not in ids:
            ids[key] = len(vertices)
            angle = angles[j] if key[1] is not None else 0.0
            vertices.append((radius * math.cos(angle), radius * math.sin(angle), height))
        return ids[key]

    count = len(profile)
    faces = []
    for k in range(count if closed else count - 1):
        k_next = (k + 1) % count
        for j in range(sides):
            j_next = (j + 1) % columns
            loop = [corner(k, j), corner(k, j_next), corner(k_next, j_next), corner(k_next, j)]
            face = [c for position, c in enumerate(loop) if c != loop[position - 1]]
            if len(set(face)) >= 3:
                faces.append(tuple(face))

    side_count = len(faces)
    if capped:
        points = lambda: np.array(vertices)  # noqa: E731 - read after corners are made
        axis_ids = {}

        def on_axis(height):
            if height not in axis_ids:
                axis_ids[height] = len(vertices)
                vertices.append((0.0, 0.0, height))
            return axis_ids[height]

        if not closed:
            for k, outward in ((0, (0.0, 0.0, -1.0)), (count - 1, (0.0, 0.0, 1.0))):
                radius, height = profile[k]
                if radius < 1e-9:
                    continue
                ring = [corner(k, j) for j in range(columns)]
                if full:
                    faces.append(_oriented(points(), ring, np.array(outward)))
                else:
                    # a sector - in triangles from the axis, so every face is
                    # convex whatever the sweep
                    middle = on_axis(height)
                    for a, b in zip(ring, ring[1:]):
                        faces.append(_oriented(points(), (middle, a, b), np.array(outward)))

        if not full:
            for j, angle, sign in ((0, 0.0, -1.0), (columns - 1, sweep, 1.0)):
                outward = sign * np.array([-math.sin(angle), math.cos(angle), 0.0])
                cut = [corner(k, j) for k in range(count)]
                if not closed:
                    if profile[-1][0] > 1e-9:
                        cut.append(on_axis(profile[-1][1]))
                    if profile[0][0] > 1e-9:
                        cut.append(on_axis(profile[0][1]))
                cut = [c for position, c in enumerate(cut) if c != cut[position - 1]]
                if len(set(cut)) >= 3:
                    faces.append(_oriented(points(), cut, outward))

    return np.array(vertices), faces, (tuple(profile), closed, float(sweep), side_count)


def _dedupe_profile(profile):
    kept = [profile[0]]
    for point in profile[1:]:
        if abs(point[0] - kept[-1][0]) > 1e-9 or abs(point[1] - kept[-1][1]) > 1e-9:
            kept.append(point)
    return kept


def torus(sides, tube_sides, thickness, sweep, capped):
    """A donut its outer edge 1 from the centre; `thickness` is the tube's
    radius over the ring's."""
    ring = 1.0 / (1.0 + thickness)
    tube = ring * thickness
    steps = np.arange(tube_sides) * 2 * math.pi / tube_sides
    profile = [(ring + tube * math.cos(t), tube * math.sin(t)) for t in steps]
    return revolve(profile, sides, sweep, closed=True, capped=capped)


def cylinder(sides, height, sweep, capped):
    return revolve([(1.0, -height / 2), (1.0, height / 2)], sides, sweep, capped=capped)


def cone(sides, height, top, sweep, capped):
    """A cone - `top` 0 - or, with a top ring, a cut-off cone."""
    return revolve([(1.0, -height / 2), (top, height / 2)], sides, sweep, capped=capped)


def capsule(sides, rings, height, sweep, capped):
    """A cylinder `height` long with a half sphere on each end, each half
    `rings` rings from its pole to the cylinder."""
    half = height / 2
    profile = [(0.0, -half - 1.0)]
    for step in range(1, rings):
        angle = -math.pi / 2 + step * (math.pi / 2) / rings
        profile.append((math.cos(angle), -half + math.sin(angle)))
    profile += [(1.0, -half), (1.0, half)]
    for step in range(1, rings):
        angle = step * (math.pi / 2) / rings
        profile.append((math.cos(angle), half + math.sin(angle)))
    profile.append((0.0, half + 1.0))
    return revolve(_dedupe_profile(profile), sides, sweep, capped=capped)


def star(points, inner, height, capped):
    """A star `points` pointed, its points 1 from the centre and the notches
    between them `inner`, stood `height` tall."""
    count = 2 * points
    angles = np.arange(count) * math.pi / points
    radii = np.where(np.arange(count) % 2 == 0, 1.0, inner)
    outline = np.stack([radii * np.cos(angles), radii * np.sin(angles)], axis=-1)
    vertices = [(x, y, -height / 2) for x, y in outline] + [(x, y, height / 2) for x, y in outline]
    faces = []
    for i in range(count):
        j = (i + 1) % count
        faces.append((i, j, count + j, count + i))
    if capped:
        vertices += [(0.0, 0.0, -height / 2), (0.0, 0.0, height / 2)]
        bottom, top = len(vertices) - 2, len(vertices) - 1
        points_array = np.array(vertices)
        for i in range(count):
            j = (i + 1) % count
            faces.append(_oriented(points_array, (bottom, i, j), np.array([0.0, 0.0, -1.0])))
            faces.append(_oriented(points_array, (top, count + i, count + j), np.array([0.0, 0.0, 1.0])))
    return np.array(vertices), faces, None


def cuboid():
    """A unit cube, centred - a cuboid is this stretched to its sizes."""
    vertices = np.array([
        (x, y, z) for z in (-0.5, 0.5) for y in (-0.5, 0.5) for x in (-0.5, 0.5)
    ])
    faces = [
        (0, 2, 3, 1), (4, 5, 7, 6),     # bottom, top
        (0, 1, 5, 4), (2, 6, 7, 3),     # front, back
        (0, 4, 6, 2), (1, 3, 7, 5),     # left, right
    ]
    return vertices, faces, None


@functools.lru_cache(maxsize=64)
def built_shape(style, sides, tube_sides, thickness, height, top, inner, rings, capped, sweep):
    if style == TORUS:
        vertices, faces, spun = torus(sides, tube_sides, thickness, sweep, capped)
    elif style == CYLINDER:
        vertices, faces, spun = cylinder(sides, height, sweep, capped)
    elif style == CONE:
        vertices, faces, spun = cone(sides, height, top, sweep, capped)
    elif style == CAPSULE:
        vertices, faces, spun = capsule(sides, rings, height, sweep, capped)
    elif style == STAR:
        vertices, faces, spun = star(sides, inner, height, capped)
    else:
        vertices, faces, spun = cuboid()
    mesh = make_mesh(vertices, faces)
    if spun is not None:
        profile, closed, swept, side_count = spun
        mesh = mesh._replace(revolution=(profile, closed, swept), side_count=side_count)
    return mesh


def build(style, size=1.0, stretch=(1.0, 1.0, 1.0), vertices=4, sides=16, tube_sides=12,
          thickness=0.35, height=2.0, top=0.0, inner=0.5, rings=4, capped=True,
          sweep=FULL_TURN):
    """The mesh of a shape at its size and stretch."""
    if style in HULL_STYLES:
        mesh = unit_shape(style, int(vertices))
    else:
        mesh = built_shape(
            style, int(sides), int(tube_sides), round(float(thickness), 6),
            round(float(height), 6), round(float(top), 6), round(float(inner), 6),
            int(rings), bool(capped), round(float(sweep), 6),
        )
    scale = size * np.asarray(stretch, dtype=np.float64)
    return mesh._replace(vertices=mesh.vertices * scale, scale=tuple(scale))


# Frames ---
def face_frames(mesh):
    """Per face its normal, centre and flat axes (x along its longest edge,
    y across it), plus each corner-count group's faces laid flat in those
    axes - one array op per group, however many faces."""
    count = len(mesh.faces)
    normals, middles = np.zeros((count, 3)), np.zeros((count, 3))
    axis_x, axis_y = np.zeros((count, 3)), np.zeros((count, 3))
    flats = {}
    for size, (ids, corners) in mesh.groups.items():
        points = mesh.vertices[corners]
        following = np.roll(points, -1, axis=1)
        normal = unit(np.cross(points, following).sum(axis=1))
        middle = points.mean(axis=1)
        edges = following - points
        longest = np.argmax(np.linalg.norm(edges, axis=2), axis=1)
        x = unit(edges[np.arange(len(ids)), longest])
        y = np.cross(normal, x)
        relative = points - middle[:, None]
        flats[size] = np.stack(
            [(relative * x[:, None]).sum(axis=2), (relative * y[:, None]).sum(axis=2)], axis=-1
        )
        normals[ids], middles[ids], axis_x[ids], axis_y[ids] = normal, middle, x, y
    return normals, middles, axis_x, axis_y, flats


# Filling ---
def _empty():
    return np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 3))


def _empty_2d():
    return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros((0, 2))


def _outset(polygon, distance):
    """A convex polygon (counter-clockwise, 2D) with every edge moved
    `distance` outwards: each corner is where its two edges' moved lines
    meet. Growing a convex polygon never folds it, so that always holds."""
    starts, ends = polygon, np.roll(polygon, -1, axis=0)
    edges = ends - starts
    lengths = np.linalg.norm(edges, axis=1)
    keep = lengths > 1e-12
    starts, edges, lengths = starts[keep], edges[keep], lengths[keep]
    outward = np.stack([edges[:, 1], -edges[:, 0]], axis=-1) / lengths[:, None]
    moved = starts + outward * distance

    corners = []
    for index in range(len(moved)):
        # the line of the edge before, and this one, both moved out
        p, r = moved[index - 1], edges[index - 1]
        q, s = moved[index], edges[index]
        cross = r[0] * s[1] - r[1] * s[0]
        if abs(cross) < 1e-12:
            corners.append(q)
            continue
        t = ((q[0] - p[0]) * s[1] - (q[1] - p[1]) * s[0]) / cross
        corners.append(p + r * t)
    return np.array(corners)


def _inset(polygon, margin):
    """A convex polygon (counter-clockwise, 2D) with every edge moved
    `margin` inwards - each edge's half plane clipped in turn, so edges too
    short to survive drop out rather than crossing over. Empty when nothing
    is left. A negative margin moves the edges outwards instead."""
    if margin < 0:
        return _outset(polygon, -margin)
    if margin == 0:
        return polygon
    result = polygon
    for start, end in zip(polygon, np.roll(polygon, -1, axis=0)):
        edge = end - start
        length = np.linalg.norm(edge)
        if length < 1e-12:
            continue
        outward = np.array([edge[1], -edge[0]]) / length
        limit = float(outward @ start) - margin
        clipped = []
        for point, following in zip(result, np.roll(result, -1, axis=0)):
            here, there = point @ outward - limit, following @ outward - limit
            if here <= 0:
                clipped.append(point)
            if (here <= 0) != (there <= 0):
                clipped.append(point + (following - point) * (here / (here - there)))
        if len(clipped) < 3:
            return np.zeros((0, 2))
        result = np.array(clipped)
    return result


def _spans(polygon, heights):
    """(left, right) of a convex polygon along each horizontal line."""
    start, end = polygon, np.roll(polygon, -1, axis=0)
    y = heights[:, None]
    low = np.minimum(start[:, 1], end[:, 1])[None]
    high = np.maximum(start[:, 1], end[:, 1])[None]
    crosses = (y >= low - 1e-9) & (y <= high + 1e-9)
    rise = (end[:, 1] - start[:, 1])[None]
    flat = np.abs(rise) < 1e-12
    along_edge = np.clip((y - start[None, :, 1]) / np.where(flat, 1.0, rise), 0.0, 1.0)
    x = start[None, :, 0] + along_edge * (end[:, 0] - start[:, 0])[None]
    # a level edge at that height spans both its ends
    x_low = np.where(flat, np.minimum(start[:, 0], end[:, 0])[None], x)
    x_high = np.where(flat, np.maximum(start[:, 0], end[:, 0])[None], x)
    left = np.where(crosses, x_low, np.inf).min(axis=1)
    right = np.where(crosses, x_high, -np.inf).max(axis=1)
    return left, right


def _fit(room, size, spacing):
    """How many parts of `size`, `spacing` apart, fit in `room`, and the
    distance from one to the next."""
    pitch = max(size + spacing, 1e-6)
    count = np.floor((room - size) / pitch + 1e-9) + 1
    count = np.where(np.isfinite(count), count, 0)
    return np.where(room >= size - 1e-9, count, 0).clip(0).astype(int), pitch


def rows_2d(flat, width, height, margin=0.0, spacing=0.0):
    """Parts in rows across a convex face laid flat (counter-clockwise, its
    x along the rows), every part wholly inside it.

    Each row takes as many parts as fit across it and centres them; the rows
    are centred up the face. `margin` keeps every part that far in from the
    face's edges (negative: lets them out past them), and `spacing` is the
    gap between neighbours, across a row and between rows (negative: they
    overlap).

    A part spanning a row from y0 to y1 fits wherever the face is at least
    as wide at both heights: a convex face is narrowest across a band at
    one of the band's edges, so that is exact.

    Returns:
        (centres, along, up), all flat
    """
    if width <= 0 or height <= 0:
        return _empty_2d()
    polygon = _inset(flat, margin)
    if not len(polygon):
        return _empty_2d()

    bottom, top = polygon[:, 1].min(), polygon[:, 1].max()
    rows, row_pitch = _fit(np.array(top - bottom), height, spacing)
    rows = int(rows)
    if rows < 1:
        return _empty_2d()
    rows_height = height + (rows - 1) * row_pitch
    row_bottoms = bottom + (top - bottom - rows_height) / 2 + np.arange(rows) * row_pitch
    left_low, right_low = _spans(polygon, row_bottoms)
    left_high, right_high = _spans(polygon, row_bottoms + height)
    left = np.maximum(left_low, left_high)
    right = np.minimum(right_low, right_high)
    counts, pitch = _fit(right - left, width, spacing)
    total = int(counts.sum())
    if not total:
        return _empty_2d()

    row = np.repeat(np.arange(rows), counts)
    within = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
    row_width = width + (counts - 1) * pitch
    first = (left + right) / 2 - row_width / 2 + width / 2
    centres = np.stack([first[row] + within * pitch, row_bottoms[row] + height / 2], axis=-1)
    return centres, np.tile((1.0, 0.0), (total, 1)), np.tile((0.0, 1.0), (total, 1))


def rings_2d(flat, width, height, margin=0.0, spacing=0.0, overlap=0.0):
    """Parts in rings following a convex face's outline, laid flat, each
    lined up with the edge it is nearest to - no staircase along slanted
    edges.

    Ring after ring works inwards. Along every edge of a ring the parts sit
    on the edge and reach `height` in; they are kept to the stretch where
    that inner line is still nearer this edge than any other, so parts of
    neighbouring edges never cross at a corner, and every part stays inside
    the face. `margin` and `spacing` work as in rows_2d. `overlap` lets
    every row run on past its strip into its neighbours' by that many part
    heights, filling the gaps along the seams.

    Every ring at once: moving a convex face's edges in by t leaves edge i
    spanning, along its own line moved in by t, whatever every other edge's
    moved line allows - linear in t, so all depths of all edges are one
    array sum.

    Returns:
        (centres, along, up), all flat
    """
    if width <= 0 or height <= 0:
        return _empty_2d()
    edges = np.roll(flat, -1, axis=0) - flat
    lengths = np.linalg.norm(edges, axis=1)
    keep = lengths > 1e-9
    starts, edges, lengths = flat[keep], edges[keep], lengths[keep]
    if len(starts) < 3:
        return _empty_2d()
    directions = edges / lengths[:, None]
    inwards = np.stack([-directions[:, 1], directions[:, 0]], axis=-1)
    outwards = -inwards
    limits = (outwards * starts).sum(axis=1)

    # depth of each ring's outer edge; enough rings to cross the face
    step = max(height + spacing, 1e-6)
    across = np.linalg.norm(flat[:, None] - flat[None], axis=-1).max()
    rings = max(int(math.ceil((across / 2 + abs(margin) + height) / step)) + 1, 1)
    depths = margin + np.arange(rings) * step
    reach = depths + height

    # A point s along edge i's line moved in by t stays behind edge j's line
    # moved in by u while s * rate[i, j] <= room[i, j] - u - t * facing[i, j].
    rate = directions @ outwards.T
    room = limits[None, :] - starts @ outwards.T
    facing = inwards @ outwards.T
    forward, backward = rate > 1e-12, rate < -1e-12
    safe_rate = np.where(np.abs(rate) > 1e-12, rate, 1.0)[None]

    def span(t, u):
        bounds = room[None] - u[:, None, None] - t[:, None, None] * facing[None]
        ratio = bounds / safe_rate
        high = np.where(forward[None], ratio, np.inf).min(axis=2)
        low = np.where(backward[None], ratio, -np.inf).max(axis=2)
        blocked = ((~forward & ~backward)[None] & (bounds < -1e-9)).any(axis=2)
        return low, high, blocked

    # The parts' inner side must stay nearer their own edge than the others
    # moved in to the same depth - their strip. `overlap` (in part heights)
    # lets it that much further, the same at every depth, so every row runs
    # on into the neighbouring strips by the same amount and the seams
    # overlap evenly from the corners to the middle - never past the face.
    reach_past = max(overlap, 0.0) * height
    inner_low, inner_high, inner_blocked = span(
        reach, np.maximum(reach - reach_past, margin)
    )
    # and their outer side inside the face - only ever binding once they
    # reach past their strip
    outer_low, outer_high, outer_blocked = span(depths, np.full_like(depths, margin))
    low = np.maximum(inner_low, outer_low)
    high = np.minimum(inner_high, outer_high)
    room_along = np.where(inner_blocked | outer_blocked, -np.inf, high - low)

    counts, pitch = _fit(room_along, width, spacing)
    total = int(counts.sum())
    if not total:
        return _empty_2d()

    ring, edge = np.nonzero(counts)
    per = counts[ring, edge]
    ring, edge = np.repeat(ring, per), np.repeat(edge, per)
    within = np.arange(total) - np.repeat(np.cumsum(per) - per, per)
    occupied = width + (counts[ring, edge] - 1) * pitch
    middle_along = (low[ring, edge] + high[ring, edge]) / 2
    along_edge = middle_along - occupied / 2 + width / 2 + within * pitch
    centres = (
        starts[edge]
        + directions[edge] * along_edge[:, None]
        + inwards[edge] * (depths[ring] + height / 2)[:, None]
    )
    return centres, directions[edge], inwards[edge]


def fill_faces(mesh, frames, width, height, margin=0.0, spacing=0.0, follow_edges=False,
               overlap=0.0, first_face=0):
    """Parts across every face. Faces that are the same shape - every face
    of a ring on a donut, all six sides of a cube - are filled once and the
    result laid onto each of them."""
    normals, middles, axis_x, axis_y, flats = frames
    if follow_edges:
        fill_flat = functools.partial(
            rings_2d, width=width, height=height, margin=margin, spacing=spacing, overlap=overlap
        )
    else:
        fill_flat = functools.partial(
            rows_2d, width=width, height=height, margin=margin, spacing=spacing
        )

    groups = []
    for size, (ids, _) in mesh.groups.items():
        flat = flats[size]
        kept = ids >= first_face
        if not kept.any():
            continue
        ids, flat = ids[kept], flat[kept]
        # + 0.0 turns -0.0 into 0.0, so equal faces compare equal
        keys = np.round(flat, 6).reshape(len(ids), -1) + 0.0
        _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
        inverse = inverse.reshape(-1)
        for shape, sample in enumerate(first):
            centres, along, up = fill_flat(flat[sample])
            if not len(centres):
                continue
            members = ids[inverse == shape]
            x = axis_x[members][:, None, :]
            y = axis_y[members][:, None, :]
            count = len(centres)
            groups.append((
                (middles[members][:, None, :] + centres[None, :, :1] * x + centres[None, :, 1:] * y),
                np.broadcast_to(normals[members][:, None, :], (len(members), count, 3)),
                along[None, :, :1] * x + along[None, :, 1:] * y,
                up[None, :, :1] * x + up[None, :, 1:] * y,
            ))
    if not groups:
        return _empty()
    return tuple(np.concatenate([group[i].reshape(-1, 3) for group in groups]) for i in range(4))


def fill_edges(mesh, normals, width, spacing=0.0):
    """Parts along every edge, `spacing` apart, as many as fit between its
    corners, centred. They face out along the edge's bisector."""
    if width <= 0 or not len(mesh.edges):
        return _empty()
    first, second = mesh.edge_faces[:, 0], mesh.edge_faces[:, 1]
    bisectors = unit(normals[first] + np.where(second[:, None] >= 0, normals[second], 0.0))

    starts = mesh.vertices[mesh.edges[:, 0]]
    offsets = mesh.vertices[mesh.edges[:, 1]] - starts
    lengths = np.linalg.norm(offsets, axis=1)
    counts, pitch = _fit(lengths, width, spacing)
    total = int(counts.sum())
    if not total:
        return _empty()

    edge = np.repeat(np.arange(len(mesh.edges)), counts)
    within = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
    directions = offsets / np.where(lengths > 0, lengths, 1.0)[:, None]
    occupied = width + (counts - 1) * pitch
    distance = (lengths - occupied)[edge] / 2 + width / 2 + within * pitch
    centres = starts[edge] + directions[edge] * distance[:, None]
    out, along = bisectors[edge], directions[edge]
    return centres, out, along, np.cross(out, along)


def fill_corners(mesh, normals):
    """A part on every corner, facing out along the average of the faces
    that meet there, turned to line up with one of its edges."""
    summed = np.zeros_like(mesh.vertices)
    np.add.at(summed, mesh.corner_vertex, normals[mesh.corner_face])
    corners = mesh.corners
    out = unit(summed[corners])
    toward = mesh.vertices[mesh.neighbours] - mesh.vertices[corners]
    along = unit(toward - out * (toward * out).sum(axis=1, keepdims=True))
    return mesh.vertices[corners], out, along, np.cross(out, along)


def _corner_to_corner(length, size, spacing):
    """Where parts go across `length` so the first and last touch its ends,
    the room between shared out evenly. One part on its own sits in the
    middle.

    With a positive `spacing` it is as many as fit at least that far apart,
    so any room left over widens the gaps. Otherwise it is as few as close
    every gap - no two neighbours further apart than `spacing` - so a length
    that isn't a whole number of parts gets them overlapping a little rather
    than a hole, and a face narrower than one part still gets one."""
    if spacing > 0:
        count = int(_fit(np.array(length), size, spacing)[0])
    elif length <= size + 1e-9:
        count = 1
    else:
        pitch = max(size + spacing, 1e-6)
        count = int(math.ceil((length - size) / pitch - 1e-9)) + 1
    if count < 1:
        return np.zeros(0)
    if count == 1:
        return np.array([length / 2])
    return size / 2 + np.arange(count) * (length - size) / (count - 1)


def fill_rectangles(mesh, frames, width, height, spacing=0.0, offset=0.0):
    """A grid over every face of a box, corner to corner: each row and
    column starts at one edge of the face and ends at the other, parts at
    least `spacing` apart. Rows run along each face's longer side. `offset`
    moves every face's parts out from the box (in, if negative).

    Returns:
        (centres, normals, along, up)
    """
    normals = frames[0]
    groups = []
    for face_index, face in enumerate(mesh.faces):
        corners = mesh.vertices[list(face)]
        side_a, side_b = corners[1] - corners[0], corners[-1] - corners[0]
        if np.linalg.norm(side_b) > np.linalg.norm(side_a):
            side_a, side_b = side_b, side_a
        length_a, length_b = np.linalg.norm(side_a), np.linalg.norm(side_b)
        if length_a < 1e-9 or length_b < 1e-9:
            continue
        along = side_a / length_a
        normal = normals[face_index]
        up = np.cross(normal, along)
        across = _corner_to_corner(length_a, width, spacing)
        rising = _corner_to_corner(length_b, height, spacing)
        if not len(across) or not len(rising):
            continue
        # the grid's origin is the corner the two sides leave from, and up
        # may point either way along the second side
        start = corners[0] + (side_b if (up @ side_b) < 0 else 0.0)
        x, y = np.meshgrid(across, rising, indexing="ij")
        count = x.size
        centres = start + x.reshape(-1, 1) * along + y.reshape(-1, 1) * up + normal * offset
        groups.append((
            centres,
            np.tile(normal, (count, 1)),
            np.tile(along, (count, 1)),
            np.tile(up, (count, 1)),
        ))
    if not groups:
        return _empty()
    return tuple(np.concatenate([group[i] for group in groups]) for i in range(4))


def fill_revolution(mesh, width, height, margin=0.0, spacing=0.0):
    """Parts over a spun shape's side as one smooth surface - rings of them
    up its profile, each ring holding as many as fit around it - where its
    narrow faces one by one would hold none.

    Rows are spaced by the part's height along the profile; each ring's
    parts by their width around it, counted at the ring's own radius. A
    profile that ends on the axis (a cone's point, a capsule's poles) gets
    one part there once a ring is too small to hold any. `margin` keeps
    parts in from an open profile's ends and a short sweep's cut edges, and
    `spacing` is the gap between neighbours both ways. Measured on the
    shape as stretched, so the parts still meet on a stretched one.

    Returns:
        (centres, normals, along, up)
    """
    if width <= 0 or height <= 0:
        return _empty()
    profile, closed, sweep = mesh.revolution
    axes = np.asarray(mesh.scale, dtype=np.float64)
    across = max(axes[0], axes[1])
    shape_profile = np.array(profile, dtype=np.float64)
    measured = shape_profile * (across, axes[2])

    ends = np.roll(shape_profile, -1, axis=0) if closed else shape_profile[1:]
    starts = shape_profile if closed else shape_profile[:-1]
    measured_ends = np.roll(measured, -1, axis=0) if closed else measured[1:]
    measured_starts = measured if closed else measured[:-1]
    lengths = np.linalg.norm(measured_ends - measured_starts, axis=1)
    keep = lengths > 1e-12
    starts, ends, lengths = starts[keep], ends[keep], lengths[keep]
    if not len(lengths):
        return _empty()
    reached = np.concatenate([[0.0], np.cumsum(lengths)])
    total = reached[-1]

    # where along the profile each ring sits
    if closed:
        rows = int(math.floor(total / max(height + spacing, 1e-6) + 1e-9))
        if rows < 1:
            return _empty()
        distance = (np.arange(rows) + 0.5) * total / rows
    else:
        rows, row_pitch = _fit(np.array(total - 2 * margin), height, spacing)
        rows = int(rows)
        if rows < 1:
            return _empty()
        used = height + (rows - 1) * row_pitch
        distance = margin + (total - 2 * margin - used) / 2 + height / 2 + np.arange(rows) * row_pitch

    segment = np.clip(np.searchsorted(reached, distance, side="right") - 1, 0, len(lengths) - 1)
    t = ((distance - reached[segment]) / lengths[segment])[:, None]
    point = starts[segment] + (ends[segment] - starts[segment]) * t
    tangent = unit(ends[segment] - starts[segment])
    # out of the side, square to the profile - radius and height
    out = np.stack([tangent[:, 1], -tangent[:, 0]], axis=-1)
    ring_radius = point[:, 0] * across

    full = sweep >= FULL_TURN - 1e-6
    step = max(width + spacing, 1e-6)
    if full:
        counts = np.floor(FULL_TURN * ring_radius / step + 1e-9).astype(int).clip(0)
        # a ring too small for even one part, on the axis: one part there
        at_pole = (counts == 0) & (ring_radius < width)
        counts = np.where(at_pole, 1, counts)
        pitch = np.where(counts > 0, FULL_TURN / np.maximum(counts, 1), 0.0)
    else:
        counts, around_pitch = _fit(sweep * ring_radius - 2 * margin, width, spacing)
        at_pole = np.zeros(rows, bool)
        pitch = around_pitch / np.maximum(ring_radius, 1e-9)
    total_parts = int(counts.sum())
    if not total_parts:
        return _empty()

    row = np.repeat(np.arange(rows), counts[:rows])
    within = np.arange(total_parts) - np.repeat(np.cumsum(counts) - counts, counts)
    if full:
        angle = (within + 0.5) * pitch[row]
    else:
        angle = sweep / 2 + (within - (counts[row] - 1) / 2) * pitch[row]
    radius = np.where(at_pole[row], 0.0, point[row, 0])
    cos, sin = np.cos(angle), np.sin(angle)

    centres = np.stack([radius * cos, radius * sin, point[row, 1]], axis=-1)
    normals = np.stack([out[row, 0] * cos, out[row, 0] * sin, out[row, 1]], axis=-1)
    along = np.stack([-sin, cos, np.zeros_like(cos)], axis=-1)
    return frames_stretch(centres, unit(normals), along, axes)


def fill(mesh, width, height, faces_on=True, edges_on=False, corners_on=False, margin=0.0,
         spacing=0.0, follow_edges=False, overlap=0.0):
    """Every part on a shape: (centres, normals, along, up)."""
    frames = face_frames(mesh)
    groups = []
    if faces_on:
        if mesh.revolution is not None:
            groups.append(fill_revolution(mesh, width, height, margin, spacing))
        groups.append(fill_faces(
            mesh, frames, width, height, margin, spacing, follow_edges, overlap,
            first_face=mesh.side_count if mesh.revolution is not None else 0,
        ))
    if edges_on:
        groups.append(fill_edges(mesh, frames[0], width, spacing))
    if corners_on:
        groups.append(fill_corners(mesh, frames[0]))
    if not groups:
        return _empty()
    return tuple(np.concatenate([group[i] for group in groups]) for i in range(4))


def fill_face(points, width, height, margin=0.0, spacing=0.0, follow_edges=False, overlap=0.0):
    """One face's parts - fill() on a shape of that face alone."""
    mesh = make_mesh(points, [tuple(range(len(points)))])
    return fill_faces(mesh, face_frames(mesh), width, height, margin, spacing, follow_edges,
                      overlap)


def fill_face_rings(points, width, height, margin=0.0, spacing=0.0, overlap=0.0):
    return fill_face(points, width, height, margin, spacing, True, overlap)
