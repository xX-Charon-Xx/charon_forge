"""Forging a QR code out of parts - The Forge's "Forge a QR Code".

Every dark module of the code (utils/qr_code.py) has to be covered by the
part without it spilling onto a light one, in as few parts as possible. The
part - STORAGEPANEL, a flat panel about 2.4 times as long as it is wide - can
be scaled, which export keeps (Up and At are written with their length, see
Group.extract_pos_up_at), but only evenly: it always keeps its proportions.

  1. The dark modules are split into all dark rectangles, chosen greedily by
     how many new modules each covers per part it costs (plan_rectangles).
     Rectangles may overlap - a module covered twice costs nothing - so the
     long runs and blocks of a QR code are taken whole.
  2. Each rectangle is covered by the fewest panels that fit it exactly
     (plan_panels): scaled to its full height and repeated along it, or
     scaled to its full length and stacked, whichever of those - either way
     round - takes fewer. Panels overlap each other rather than overhang.

Everything here is in modules; build_qr_code turns it into placed parts.
"""

import heapq
import math

import bpy
import mathutils
import numpy as np

from . import loading_overlay, qr_code

PART_ID = "STORAGEPANEL"

EPSILON = 1e-6

# rounded up or down by less than this, a count is taken as exact
_FIT = 1e-4


# Planning ---
def _ceil(value):
    return max(1, math.ceil(value - _FIT))


def plan_panels(width, height, ratio):
    """The fewest panels covering a width x height rectangle exactly.

    Args:
        width, height (float): The rectangle, in modules.
        ratio (float): The panel's long side over its short side.

    Returns:
        list: (centre x, centre y, long side along x, short side) per panel,
            relative to the rectangle's corner, in modules.
    """
    best = None
    for along_x in (True, False):
        length, across = (width, height) if along_x else (height, width)
        # a panel's short side can't be more than the rectangle across, nor
        # its long side more than the rectangle along it
        largest = min(across, length / ratio)
        candidates = {largest}
        for count in range(1, int(math.ceil(across * ratio / length)) + 3):
            candidates.add(across / count)
            candidates.add(length / (ratio * count))
        for short in candidates:
            if short > largest + EPSILON or short <= EPSILON:
                continue
            rows = _ceil(across / short)
            columns = _ceil(length / (ratio * short))
            cost = rows * columns
            if best is None or cost < best[0] or (cost == best[0] and short > best[3]):
                best = (cost, along_x, rows, short, columns)

    _cost, along_x, rows, short, columns = best
    length, across = (width, height) if along_x else (height, width)
    long_side = ratio * short

    def centres(total, piece, count):
        if count == 1:
            return [total / 2]
        return [piece / 2 + index * (total - piece) / (count - 1) for index in range(count)]

    panels = []
    for across_centre in centres(across, short, rows):
        for along_centre in centres(length, long_side, columns):
            if along_x:
                panels.append((along_centre, across_centre, True, short))
            else:
                panels.append((across_centre, along_centre, False, short))
    return panels


def plan_rectangles(modules, ratio):
    """All dark rectangles covering every dark module, chosen for the fewest
    panels between them.

    Returns:
        list: (x, y, width, height) per rectangle, in modules, y downwards.
    """
    size = len(modules)
    dark = [[bool(cell) for cell in row] for row in modules]

    # how many dark modules run down from each one
    down = [[0] * size for _ in range(size + 1)]
    for y in range(size - 1, -1, -1):
        for x in range(size):
            down[y][x] = down[y + 1][x] + 1 if dark[y][x] else 0

    cost_cache = {}

    def cost(width, height):
        key = (width, height)
        if key not in cost_cache:
            cost_cache[key] = len(plan_panels(width, height, ratio))
        return cost_cache[key]

    # every widest-for-its-height dark rectangle with a given top left corner
    candidates = []
    for y in range(size):
        for x in range(size):
            if not dark[y][x]:
                continue
            height = size
            width = 0
            while x + width < size and dark[y][x + width]:
                height = min(height, down[y][x + width])
                width += 1
                candidates.append((x, y, width, height))

    covered = [[False] * size for _ in range(size)]
    remaining = sum(map(sum, dark))

    def gain(rectangle):
        x, y, width, height = rectangle
        return sum(
            1 for row in range(y, y + height) for column in range(x, x + width)
            if not covered[row][column]
        )

    # lazy greedy: a rectangle's gain only ever falls, so one popped whose
    # stored score is still current is the best there is
    heap = [(-(width * height) / cost(width, height), index)
            for index, (x, y, width, height) in enumerate(candidates)]
    heapq.heapify(heap)

    chosen = []
    while remaining and heap:
        stored, index = heapq.heappop(heap)
        rectangle = candidates[index]
        new = gain(rectangle)
        if new == 0:
            continue
        score = -new / cost(rectangle[2], rectangle[3])
        if heap and score > heap[0][0] + EPSILON:
            heapq.heappush(heap, (score, index))
            continue
        x, y, width, height = rectangle
        for row in range(y, y + height):
            for column in range(x, x + width):
                covered[row][column] = True
        remaining -= new
        chosen.append(rectangle)
    return chosen


def plan(modules, ratio):
    """Every panel of the code: (centre x, centre y, long side along x, short
    side), in modules, y downwards."""
    panels = []
    for x, y, width, height in plan_rectangles(modules, ratio):
        for centre_x, centre_y, along_x, short in plan_panels(width, height, ratio):
            panels.append((x + centre_x, y + centre_y, along_x, short))
    return panels


# Building ---
def measure_part(mesh):
    """The panel's axes, read off its mesh: (long axis, short axis, thin axis,
    their lengths, the bounding box centre), axes as 0/1/2."""
    count = len(mesh.vertices)
    coords = np.empty(count * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", coords)
    points = coords.reshape(-1, 3)
    low, high = points.min(axis=0), points.max(axis=0)
    extents = high - low
    long_axis, short_axis, thin_axis = [int(axis) for axis in np.argsort(-extents)]
    return long_axis, short_axis, thin_axis, extents, (low + high) / 2


def _panel_rotation(long_axis, short_axis, thin_axis, long_along_x):
    """The part's rotation lying flat, long side along X or Y, turned over so
    the side opposite its front faces up - the side the code is read from."""
    rotation = mathutils.Matrix(((0.0,) * 3,) * 3)
    long_world, short_world = (0, 1) if long_along_x else (1, 0)
    rotation[long_world][long_axis] = 1.0
    rotation[short_world][short_axis] = 1.0
    rotation[2][thin_axis] = -1.0
    if rotation.determinant() < 0:
        # turned half round in the plane rather than mirrored
        rotation[short_world][short_axis] = -1.0
    return rotation


def build_qr_code(text, level="M", module_size=1.0, upright=False, collection_name=None):
    """Forge a QR code out of panels at the 3D cursor, grouped into one
    object whose origin is the middle of the code.

    Args:
        text (str): What the code says.
        level (str): Error correction, "L", "M", "Q" or "H".
        module_size (float): One module, in metres.
        upright (bool): Standing up facing -Y, rather than lying flat.

    Returns:
        tuple: (the group, the number of modules along a side, the number of
        panels in it).

    Raises:
        qr_code.QRCodeError: When the text doesn't fit a QR code.
    """
    from .. import builder as charon_builder
    from ..objects.group import Group

    modules = qr_code.encode(text, level)
    size = len(modules)

    first = charon_builder.add_part(PART_ID).object
    long_axis, short_axis, thin_axis, extents, centre = measure_part(first.data)
    long_length, short_length, thin_length = (
        extents[long_axis], extents[short_axis], extents[thin_axis]
    )
    ratio = long_length / short_length
    panels = plan(modules, ratio)

    collection = bpy.data.collections.new(collection_name or "QR Code")
    bpy.context.scene.collection.children.link(collection)

    cursor = bpy.context.scene.cursor.location.copy()
    placement = mathutils.Matrix.Translation(cursor)
    if upright:
        placement = placement @ mathutils.Matrix.Rotation(math.radians(90.0), 4, "X")

    # the panels' faces flush, whatever their size
    largest_scale = max(short for _x, _y, _along_x, short in panels) * module_size / short_length
    top = thin_length * largest_scale
    local_centre = mathutils.Vector(centre)

    objects = []
    order = len(bpy.data.objects)
    for index, (centre_x, centre_y, along_x, short) in enumerate(panels):
        loading_overlay.step("Placing panels", index / len(panels))
        scale = short * module_size / short_length
        rotation = _panel_rotation(long_axis, short_axis, thin_axis, along_x)

        target = mathutils.Vector((
            (centre_x - size / 2) * module_size,
            (size / 2 - centre_y) * module_size,
            top - thin_length * scale / 2,
        ))
        # the part's origin isn't the middle of it
        location = target - rotation @ (local_centre * scale)
        matrix = (mathutils.Matrix.Translation(location)
                  @ rotation.to_4x4()
                  @ mathutils.Matrix.Scale(scale, 4))

        bpy_object = first if index == 0 else first.copy()
        for old in list(bpy_object.users_collection):
            old.objects.unlink(bpy_object)
        collection.objects.link(bpy_object)
        bpy_object.matrix_world = placement @ matrix
        bpy_object["order"] = order + index
        objects.append(bpy_object)

    # one group, its origin at the middle of the code - the cursor, which
    # the panels were laid out around - turned upright with it if it is
    loading_overlay.step("Grouping panels", show=True)
    group = Group.group_objects(objects, placement)
    if group is None:
        raise RuntimeError("the panels could not be grouped")
    group.name = collection.name
    group["order"] = order

    return group, size, len(objects)
