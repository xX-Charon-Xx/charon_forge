"""A loading card in the middle of the 3D viewport while heavy work runs.

Blender draws nothing while an operator runs, so an import or a save file
write just freezes the window. Work wrapped in loading() can put a card up
over every 3D viewport - a title, what it is doing now and a bar - and keep it
moving:

    with loading_overlay.loading("Importing ship"):
        for index, part in enumerate(parts):
            loading_overlay.step("Placing parts", fraction=index / len(parts))
            ...

The card only comes up once the work has run for DELAY seconds, so quick
work never flashes it. It can only be drawn from inside the work, so step()
is what shows and redraws it: call it in loops (it is cheap, and redraws at
most every MIN_INTERVAL), and with show=True right before a single long call
that can't be stepped through - reading a save file, say - so the card is up
before the wait rather than after it. The bar fills to `fraction` when there
is one, and slides back and forth when there isn't.

Nested loading() blocks share the outer card, the inner title reading as the
detail line under it. Outside of any loading() block step() does nothing, so
library code can call it freely.
"""

import functools
import math
from contextlib import contextmanager
from time import perf_counter

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

# How long work runs before the card comes up, in seconds.
DELAY = 0.5
# The least time between two redraws, and how many times the last redraw's
# own cost to wait at least - so a heavy scene isn't slowed by redrawing it.
MIN_INTERVAL = 0.05
COST_RATIO = 4.0

FONT_ID = 0

# Sizes, in pixels at a UI scale of 1.
CARD_WIDTH = 340
CARD_PADDING = 16
CARD_RADIUS = 8
TITLE_SIZE = 14
DETAIL_SIZE = 11
LINE_GAP = 8
BAR_HEIGHT = 6
BAR_GAP = 12
# the sliding segment of a bar with no fraction, as a share of the bar
SEGMENT = 0.3
# seconds for the sliding segment to go across and back
SWEEP_PERIOD = 1.6

# Colours, RGBA.
SHADE_COLOUR = (0.0, 0.0, 0.0, 0.25)
CARD_COLOUR = (0.11, 0.11, 0.12, 0.94)
BORDER_COLOUR = (1.0, 1.0, 1.0, 0.08)
TITLE_COLOUR = (0.97, 0.97, 0.97, 1.0)
DETAIL_COLOUR = (0.66, 0.69, 0.74, 1.0)
TRACK_COLOUR = (1.0, 1.0, 1.0, 0.10)
BAR_COLOUR = (0.33, 0.62, 1.0, 1.0)
SHEEN_COLOUR = (1.0, 1.0, 1.0, 0.22)

# kept across a reload of this module, so the old handler can still be removed
if "_state" not in globals():
    _state = None


class _Loading(object):
    """The card being shown, or waiting to be."""

    def __init__(self, title, delay):
        self.title = title
        self.detail = ""
        self.fraction = None
        self.delay = delay
        self.started = perf_counter()
        self.next_draw = 0.0
        self.handler = None

    @property
    def visible(self):
        return self.handler is not None

    def show(self):
        self.handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_callback, (), "WINDOW", "POST_PIXEL"
        )

    def redraw(self):
        started = perf_counter()
        _redraw_viewports_now()
        finished = perf_counter()
        self.next_draw = finished + max(MIN_INTERVAL, (finished - started) * COST_RATIO)

    def close(self):
        if self.handler is None:
            return
        bpy.types.SpaceView3D.draw_handler_remove(self.handler, "WINDOW")
        self.handler = None
        # the next ordinary redraw, once the work is done, clears the card
        for _, _, region in _viewport_regions():
            region.tag_redraw()


# Public ---
@contextmanager
def loading(title, delay=DELAY):
    """Show a loading card over the 3D viewports while the block runs, once
    it has run for `delay` seconds - see step()."""
    global _state
    if bpy.app.background:
        yield
        return

    if _state is not None:
        # inside another loading(): its card carries on, reading this title
        # as what it is doing now
        state = _state
        previous = (state.detail, state.fraction)
        state.detail, state.fraction = title, None
        try:
            yield
        finally:
            if _state is state:
                state.detail, state.fraction = previous
        return

    state = _state = _Loading(title, delay)
    try:
        yield
    finally:
        _state = None
        try:
            state.close()
        except (ReferenceError, RuntimeError, ValueError) as error:
            print("Charon Forge: loading overlay:", error)


def step(detail=None, fraction=None, show=False):
    """Say how the work is getting on, and show or redraw the card when due.

    Args:
        detail (str): What is being done now, the line under the title.
        fraction (float): How far through, 0 to 1, or None to leave it.
        show (bool): Put the card up now, delay or not, and redraw it - for
            right before one long call that can't be stepped through.
    """
    state = _state
    if state is None:
        return
    if detail is not None and detail != state.detail:
        state.detail = detail
        state.fraction = None
    if fraction is not None:
        state.fraction = min(max(fraction, 0.0), 1.0)

    now = perf_counter()
    if not show:
        if now < state.next_draw:
            return
        if not state.visible and now - state.started < state.delay:
            return
    try:
        if not state.visible:
            state.show()
        state.redraw()
    except (ReferenceError, RuntimeError, ValueError, TypeError) as error:
        # never let the card stop the work it is showing; this one just
        # stops drawing
        print("Charon Forge: loading overlay:", error)
        state.next_draw = float("inf")


def while_running(title, delay=DELAY):
    """Decorate an operator's execute so it runs inside loading(title)."""
    def decorate(execute):
        @functools.wraps(execute)
        def wrapper(self, context):
            with loading(title, delay):
                return execute(self, context)
        return wrapper
    return decorate


# Redrawing ---
def _viewport_regions():
    """(window, area, region) of every 3D viewport's main region."""
    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return
    for window in window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type == "WINDOW":
                    yield window, area, region


def _redraw_viewports_now():
    """Draw the 3D viewports and put them on screen, in the middle of an
    operator. Only the viewports are tagged, so only they are drawn."""
    regions = list(_viewport_regions())
    if not regions:
        return
    # the work has usually added or removed objects since the last update,
    # and a viewport drawn from a stale depsgraph can reach freed data
    updated = set()
    for window, _, region in regions:
        view_layer = window.view_layer
        if view_layer is not None and view_layer.as_pointer() not in updated:
            updated.add(view_layer.as_pointer())
            view_layer.depsgraph.update()
        region.tag_redraw()
    window, area, region = regions[0]
    with bpy.context.temp_override(window=window, area=area, region=region):
        # draws every tagged region, in every window, and swaps
        bpy.ops.wm.redraw_timer(type="DRAW_SWAP", iterations=1)


# Drawing ---
def _rounded_rect_tris(x, y, width, height, radius, segments=6):
    """Triangles filling a rectangle with rounded corners."""
    radius = max(0.0, min(radius, width / 2, height / 2))
    centres = (
        (x + width - radius, y + height - radius, 0.0),
        (x + radius, y + height - radius, 0.5 * math.pi),
        (x + radius, y + radius, math.pi),
        (x + width - radius, y + radius, 1.5 * math.pi),
    )
    outline = []
    for cx, cy, start in centres:
        for index in range(segments + 1):
            angle = start + 0.5 * math.pi * index / segments
            outline.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    middle = (x + width / 2, y + height / 2)
    tris = []
    for index, point in enumerate(outline):
        tris.extend((middle, point, outline[(index + 1) % len(outline)]))
    return tris


def _fill(shader, tris, colour):
    if not tris:
        return
    batch = batch_for_shader(shader, "TRIS", {"pos": tris})
    shader.uniform_float("color", colour)
    batch.draw(shader)


def _rect(shader, x, y, width, height, colour, radius=0.0):
    if width <= 0 or height <= 0:
        return
    _fill(shader, _rounded_rect_tris(x, y, width, height, radius), colour)


def _fit_text(text, max_width):
    if blf.dimensions(FONT_ID, text)[0] <= max_width:
        return text
    while text and blf.dimensions(FONT_ID, text + "...")[0] > max_width:
        text = text[:-1]
    return text.rstrip() + "..."


def _draw_text(text, x, y, size, colour):
    blf.size(FONT_ID, size)
    blf.color(FONT_ID, *colour)
    blf.position(FONT_ID, x, y, 0)
    blf.draw(FONT_ID, text)


def _draw_bar(shader, x, y, width, height, fraction, now):
    radius = height / 2
    _rect(shader, x, y, width, height, TRACK_COLOUR, radius)
    if fraction is None:
        # a segment sliding across and back, easing at the ends
        phase = (now % SWEEP_PERIOD) / SWEEP_PERIOD
        position = 0.5 - 0.5 * math.cos(2.0 * math.pi * phase)
        segment = width * SEGMENT
        _rect(shader, x + (width - segment) * position, y, segment, height, BAR_COLOUR, radius)
        return

    filled = width * fraction
    _rect(shader, x, y, filled, height, BAR_COLOUR, radius)
    # a sheen running along the filled part, so it still moves while the
    # fraction doesn't
    if filled > height * 2:
        sheen = min(filled, width * 0.15)
        phase = (now % SWEEP_PERIOD) / SWEEP_PERIOD
        start = x - sheen + (filled + sheen) * phase
        left, right = max(start, x), min(start + sheen, x + filled)
        _rect(shader, left, y, right - left, height, SHEEN_COLOUR, radius)


def _draw_callback():
    state = _state
    region = bpy.context.region
    if state is None or region is None:
        return
    try:
        scale = bpy.context.preferences.system.ui_scale
        now = perf_counter()
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        gpu.state.blend_set("ALPHA")

        _rect(shader, 0, 0, region.width, region.height, SHADE_COLOUR)

        padding = CARD_PADDING * scale
        width = min(CARD_WIDTH * scale, region.width - 2 * padding)
        inner = width - 2 * padding
        if inner <= 0:
            return
        height = (
            padding * 2 + TITLE_SIZE * scale + LINE_GAP * scale
            + DETAIL_SIZE * scale + BAR_GAP * scale + BAR_HEIGHT * scale
        )
        x = (region.width - width) / 2
        y = (region.height - height) / 2

        border = max(1.0, scale)
        _rect(shader, x - border, y - border, width + 2 * border, height + 2 * border,
              BORDER_COLOUR, CARD_RADIUS * scale + border)
        _rect(shader, x, y, width, height, CARD_COLOUR, CARD_RADIUS * scale)

        # the percentage, when there is one, sits right of the title
        percent = ""
        percent_width = 0.0
        if state.fraction is not None:
            percent = "%d%%" % round(state.fraction * 100)
            blf.size(FONT_ID, DETAIL_SIZE * scale)
            percent_width = blf.dimensions(FONT_ID, percent)[0]

        title_y = y + height - padding - TITLE_SIZE * scale
        blf.size(FONT_ID, TITLE_SIZE * scale)
        title = _fit_text(state.title, inner - percent_width - LINE_GAP * scale)
        _draw_text(title, x + padding, title_y, TITLE_SIZE * scale, TITLE_COLOUR)
        if percent:
            _draw_text(percent, x + width - padding - percent_width, title_y,
                       DETAIL_SIZE * scale, DETAIL_COLOUR)

        detail_y = title_y - LINE_GAP * scale - DETAIL_SIZE * scale
        blf.size(FONT_ID, DETAIL_SIZE * scale)
        detail = _fit_text(state.detail or "Please wait...", inner)
        _draw_text(detail, x + padding, detail_y, DETAIL_SIZE * scale, DETAIL_COLOUR)

        _draw_bar(shader, x + padding, y + padding, inner, BAR_HEIGHT * scale,
                  state.fraction, now)
    except (AttributeError, ReferenceError, ValueError) as error:
        print("Charon Forge: loading overlay:", error)
    finally:
        gpu.state.blend_set("NONE")
