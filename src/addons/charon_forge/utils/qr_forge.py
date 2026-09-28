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

Everything here is in modules; objects/shapes/qr.py lays the panels out as
one forged object.
"""

import heapq
import math


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
