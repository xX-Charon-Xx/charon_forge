"""The Watchtower's text overlay in the 3D viewport.

Charon Forge's own version of the base builder addon's viewport_overlay.py,
drawn as blocks of text in the bottom or top left corner of the viewport:

  - Base: the base or corvette the scene was imported from, its type
    (planet base, corvette, freighter, space base, space station base...)
    and the part count, the parts inside groups included.
  - Active Part: the selected part's id, name, colour and material.
  - Over the ship's primary cockpit and landing bay (the optimiser panel's
    picks), a floating label naming each.

It reads nothing of that addon's but, when it is loaded, the base its
importer brought in (scene.nms_base_tool), so it works on its own. What is
shown, and where, is in the addon preferences - see the Watchtower panel.
"""

import os
import re

import blf
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from ..addon_preferences import get_addon_preferences
from ..materials.properties import PROP_READONLY_COLOUR, PROP_READONLY_MATERIAL
from . import dictionary

POSITION_BOTTOM = "Bottom"
POSITION_TOP = "Top"

FONT_ID = 0

# Sizes, in pixels at a UI scale of 1.
TITLE_SIZE = 12
TEXT_SIZE = 11
TITLE_GAP = 6
ROW_HEIGHT = 16
COLUMN_GAP = 10
BLOCK_GAP = 18
MAX_VALUE_WIDTH = 260

# Where the corners start, clear of the toolbar and the view name.
BOTTOM_MARGIN = (20, 24)
TOP_MARGIN = (60, 110)

# Colours, RGBA.
TITLE_COLOUR = (0.97, 0.97, 0.97, 1.0)
MUTED_TITLE_COLOUR = (0.70, 0.70, 0.70, 1.0)
KEY_COLOUR = (0.66, 0.69, 0.74, 1.0)
VALUE_COLOUR = (0.95, 0.95, 0.95, 1.0)

# The game's PersistentBaseTypes, as they read in the overlay.
BASE_TYPES = {
    "HomePlanetBase": "Planet Base",
    "ExternalPlanetBase": "External Base",
    "PlayerShipBase": "Corvette",
    "FreighterBase": "Freighter",
    "PlayerSpaceBase": "Space Base",
    "PlayerSpaceStationBase": "Space Station Base",
}
CORVETTE = "PlayerShipBase"

# kept across a reload of this module, so the old handler can still be removed
if "_draw_handler" not in globals():
    _draw_handler = None


# Text ---
def to_title_case(text):
    """Title case, leaving anything in brackets as it is."""
    parts = re.split(r"(\([^)]*\))", text)
    return "".join(part if part.startswith("(") else part.title() for part in parts)


def text_width(text):
    return blf.dimensions(FONT_ID, text)[0]


def fit_text(text, max_width):
    """The text, cut short with an ellipsis if it is wider than max_width."""
    if text_width(text) <= max_width:
        return text
    while text and text_width(text + "...") > max_width:
        text = text[:-1]
    return text.rstrip() + "..."


def draw_text(text, x, y, colour, size):
    blf.size(FONT_ID, size)
    blf.color(FONT_ID, *colour)
    blf.position(FONT_ID, x, y, 0)
    blf.draw(FONT_ID, text)


# Contents ---
def get_part_count(scene):
    """Every part in the scene, the parts inside groups and The Forge's
    shapes included."""
    count = 0
    for obj in scene.objects:
        if "ObjectID" in obj:
            count += 1
        if "GroupID" in obj:
            count += _group_part_count(obj)
    return count


def _group_part_count(obj):
    """How many parts a group, or a shape made in The Forge, stands for."""
    part_count = obj.get("part_count")
    if part_count is not None:
        return int(part_count)
    # a shape saved before shapes kept their count on the object has it in
    # its settings only
    settings = getattr(obj, "charon_forged", None)
    if settings is not None and settings.form:
        return settings.part_count
    return 0


def get_base_info(scene):
    """(name, base type) of what the scene was imported from; either can be None."""
    # the base builder addon's importer
    base_tool = getattr(scene, "nms_base_tool", None)
    if base_tool is not None:
        name = getattr(base_tool, "string_base", "")
        if name and getattr(base_tool, "string_address", ""):
            return name, getattr(base_tool, "string_base_type", "") or None

    # a ship file brought in through the Crossing panel is always a corvette
    crossing = getattr(scene, "charon_crossing", None)
    if crossing is not None and crossing.source_file:
        name = os.path.splitext(os.path.basename(crossing.source_file))[0]
        return name, CORVETTE
    return None, None


def base_type_name(base_type):
    """How a base type reads: "PlayerSpaceBase" -> "Space Base"."""
    if base_type in BASE_TYPES:
        return BASE_TYPES[base_type]
    # a type this doesn't know, "PlayerSomeNewBase" -> "Some New Base"
    return re.sub(r"(?<!^)(?=[A-Z])", " ", base_type).replace("Player ", "")


def model_id_of(bpy_object):
    """The model a part shows - a fossil bone's is in its Message."""
    from ..builder import placement
    return placement.model_id_of(bpy_object.get("ObjectID"), bpy_object.get("Message"))


# Blocks ---
class TextBlock(object):
    """A title, and rows of "key   value" under it with the values lined up."""

    def __init__(self, title, title_colour=TITLE_COLOUR):
        self.title = title
        self.title_colour = title_colour
        self.rows = []

    def add(self, key, value):
        self.rows.append((key, str(value)))

    def measure(self, scale):
        blf.size(FONT_ID, TEXT_SIZE * scale)
        max_width = MAX_VALUE_WIDTH * scale
        self.rows = [(key, fit_text(value, max_width)) for key, value in self.rows]
        self.key_width = max((text_width(key) for key, _ in self.rows), default=0)
        self.height = (TITLE_SIZE + TITLE_GAP + len(self.rows) * ROW_HEIGHT) * scale
        return self.height

    def draw(self, x, y, scale):
        """Draw with the block's bottom left at (x, y)."""
        top = y + self.height
        draw_text(self.title, x, top - TITLE_SIZE * scale, self.title_colour, TITLE_SIZE * scale)

        value_x = x + self.key_width + COLUMN_GAP * scale
        rows_top = top - (TITLE_SIZE + TITLE_GAP) * scale
        for index, (key, value) in enumerate(self.rows):
            baseline = rows_top - (index + 1) * ROW_HEIGHT * scale + 4 * scale
            draw_text(key, x, baseline, KEY_COLOUR, TEXT_SIZE * scale)
            draw_text(value, value_x, baseline, VALUE_COLOUR, TEXT_SIZE * scale)


def base_block(context):
    name, base_type = get_base_info(context.scene)
    block = TextBlock(
        name or "No Base/Corvette imported",
        title_colour=TITLE_COLOUR if name else MUTED_TITLE_COLOUR,
    )
    if base_type:
        block.add("Type", base_type_name(base_type))
    block.add("Part Count", f"{get_part_count(context.scene):,}")
    return block


def active_part_block(context):
    active_object = context.active_object
    if active_object is None or "ObjectID" not in active_object:
        return None
    if not active_object.select_get():
        return None

    object_id = str(active_object["ObjectID"]).replace("^", "")
    model_id = model_id_of(active_object)

    block = TextBlock("Active Part")
    block.add("Part ID", object_id if model_id == object_id else f"{object_id} ({model_id})")

    nice_name = dictionary.get_nice_names_diictionary().get(model_id)
    if nice_name:
        block.add("Name", to_title_case(nice_name))

    colour = active_object.get(PROP_READONLY_COLOUR)
    if colour:
        block.add("Colour", colour)
    material = active_object.get(PROP_READONLY_MATERIAL)
    if material:
        block.add("Material", material)
    return block


# Primary parts ---
MARKER_SIZE = 13
MARKER_COLOUR = (1.0, 0.82, 0.35, 1.0)
# how far above the part's highest point the label floats, in pixels
MARKER_LIFT = 14


def draw_primary_markers(context, scale):
    """A label floating over the primary cockpit and landing bay."""
    from . import optimiser_utils
    optimiser = getattr(context.scene, "charon_optimiser", None)
    region = context.region
    region_3d = getattr(context.space_data, "region_3d", None)
    if optimiser is None or region_3d is None:
        return

    primaries = set(optimiser_utils.get_primary_parts())
    labels = ((optimiser.cockpit, "Cockpit"), (optimiser.landing_bay, "Landing Bay"))
    for obj, label in labels:
        if obj is None or obj not in primaries or not obj.visible_get():
            continue
        # over the middle of the part, at its highest corner
        corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        top = max(corner.z for corner in corners)
        centre = sum(corners, Vector()) / len(corners)
        point = location_3d_to_region_2d(region, region_3d, Vector((centre.x, centre.y, top)))
        if point is None:
            continue    # behind the view

        size = MARKER_SIZE * scale
        blf.size(FONT_ID, size)
        width = text_width(label)
        draw_text(label, point.x - width / 2, point.y + MARKER_LIFT * scale, MARKER_COLOUR, size)


# Drawing ---
def _layout_corner(blocks, corner, region, scale):
    """Draw blocks stacked in a corner, the first nearest the corner's edge."""
    if corner == POSITION_BOTTOM:
        x = BOTTOM_MARGIN[0] * scale
        y = BOTTOM_MARGIN[1] * scale
        for block in blocks:
            block.draw(x, y, scale)
            y += block.height + BLOCK_GAP * scale
    else:
        x = TOP_MARGIN[0] * scale
        y = region.height - TOP_MARGIN[1] * scale
        for block in blocks:
            y -= block.height
            block.draw(x, y, scale)
            y -= BLOCK_GAP * scale


def _draw_callback():
    prefs = get_addon_preferences()
    if prefs is None or not prefs.watchtower_show_overlay:
        return

    context = bpy.context
    region = context.region
    if region is None:
        return
    scale = context.preferences.system.ui_scale

    corners = {POSITION_BOTTOM: [], POSITION_TOP: []}
    try:
        # with no background behind it, a shadow keeps the text readable
        # over whatever the scene shows there
        blf.enable(FONT_ID, blf.SHADOW)
        blf.shadow(FONT_ID, 3, 0.0, 0.0, 0.0, 1.0)
        blf.shadow_offset(FONT_ID, 1, -1)

        if prefs.watchtower_show_primary_labels:
            draw_primary_markers(context, scale)

        if prefs.watchtower_show_part_count:
            corners[prefs.watchtower_part_count_position].append(base_block(context))
        if prefs.watchtower_show_active_object:
            block = active_part_block(context)
            if block is not None:
                corners[prefs.watchtower_active_object_position].append(block)
        if not any(corners.values()):
            return

        for corner, blocks in corners.items():
            for block in blocks:
                block.measure(scale)
            if blocks:
                _layout_corner(blocks, corner, region, scale)
    except (AttributeError, ReferenceError, KeyError, ValueError) as error:
        print("Charon Forge: watchtower overlay:", error)
    finally:
        blf.disable(FONT_ID, blf.SHADOW)


def redraw_viewports():
    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return
    for window in window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def register_draw():
    """Start drawing the overlay. Returns None so it can run as a timer."""
    global _draw_handler
    unregister_draw()
    _draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        _draw_callback, (), "WINDOW", "POST_PIXEL"
    )
    redraw_viewports()
    return None


def unregister_draw():
    global _draw_handler
    if _draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, "WINDOW")
        _draw_handler = None
        redraw_viewports()
