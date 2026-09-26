"""Space stations, appended whole from models/space_station.

A station has two parts, each imported on its own or together:

    interior/  STATION_INTERIOR_<kind>.blend - its core (main hall) and runway
               (hangar), each a model, floor and roof, plus build zones
    exterior/  STATION_EXTERIOR_<kind>.blend - its body, plus build zones

They are made by the extraction pipeline the way the high res parts are, so
their materials carry the NMS_Colourise node group and are coloured through
the same object properties (materials/colouring.py). Their textures sit
beside them in models/space_station/textures; the files point at wherever
they were when they were written, so they are pointed back there on import.

A station's colours come from the game's STATIONBASE palette group, the same
palettes resources/station_colours.json and STA_COLOURS.md list - they are
read from resources/colours.json (materials/game_data.py), which holds them
too and is already loaded for the parts.

Each part is one collection, recording which part and kind it is and its
palette, and everything its import brought in is tagged - so it can be
recoloured in place, swapped for another kind or taken out again without
touching anything else in the file.
"""

import math
import os
import re
import time

import bpy

from .. import materials
from ..materials import game_data
from ..materials.colouring import apply_palette
from ..materials.properties import PROP_FINISH
from . import station_colours
from .paths import MODEL_PATH

STATION_PATH = os.path.join(MODEL_PATH, "space_station")
TEXTURE_PATH = os.path.join(STATION_PATH, "textures")

STATION_PALETTE_GROUP = "STATIONBASE"

INTERIOR = "INTERIOR"
EXTERIOR = "EXTERIOR"

# (identifier, label, description) of each part's kinds
INTERIORS = [
    ("ROUND", "Round", "The round interior"),
    ("SQUARE", "Square", "The square interior"),
    ("TRI", "Triangle", "The triangular interior"),
]
EXTERIORS = [
    ("DISK", "Disk", "The disk exterior"),
    ("EX", "Ex", "The EX exterior"),
    ("OCT", "Octagon", "The octagonal exterior"),
    ("SIMPLE", "Simple", "The simple exterior"),
    ("TET", "Tetrahedron", "The tetrahedral exterior"),
    ("TRI", "Triangle", "The triangular exterior"),
]
KINDS = {INTERIOR: INTERIORS, EXTERIOR: EXTERIORS}

# on each part's collection: which part, which kind, and which palette (-1
# for the colours it was saved with)
PROP_PART = "charon_station_part"
PROP_KIND = "charon_station"
PROP_PALETTE = "charon_station_palette"
# on every datablock an import brought in
PROP_TAG = "charon_station_data"
SAVED_PALETTE = -1

# helper volumes, not scenery - imported hidden
_HIDDEN_SUFFIXES = ("_BUILD_ZONES",)

_palette_items = []


def part_path(part, kind):
    return os.path.join(STATION_PATH, part.lower(), "STATION_%s_%s.blend" % (part, kind))


def kind_label(part, kind):
    return next((name for identifier, name, _ in KINDS[part] if identifier == kind), kind)


def station_palettes():
    """The station palettes, in the order the game lists them."""
    return game_data.group_palettes(STATION_PALETTE_GROUP)


def palette_items(self, context):
    """The station palettes for an enum, then keeping the colours it was
    saved with - the first is the default. Blender needs the list kept alive
    while it shows it."""
    global _palette_items
    items = []
    for number, entry in enumerate(station_palettes()):
        # named after its colours, with a swatch of all four
        colours = [entry[slot] for slot in ("p", "s", "t", "q")]
        items.append((
            str(entry["index"]),
            "%d  %s" % (number + 1, station_colours.colours_name(colours)),
            "The game's %s station palette: %s"
            % (entry["id"], station_colours.hex_colours(colours)),
            station_colours.swatch_icon(entry["id"], colours),
            number,
        ))
    items.append((str(SAVED_PALETTE), "As Saved",
                  "Keep the colours the station was saved with", "FILE_REFRESH", 999))
    _palette_items = items
    return items


def find_station(part=None):
    """A part's collection in this file - or with no part, either one - or
    None. A station imported before exteriors existed is an interior."""
    for collection in bpy.data.collections:
        if PROP_KIND in collection:
            if part is None or collection.get(PROP_PART, INTERIOR) == part:
                return collection
    return None


def find_stations():
    return [collection for collection in bpy.data.collections if PROP_KIND in collection]


# Visibility ---
# the two halves of every interior, each its model, floor and roof - the
# objects are named <INTERIOR>_CORE, <INTERIOR>_CORE_FLOOR, ...
SECTIONS = ("CORE", "RUNWAY")

# on the interior's collection, per section: whether its roof is kept hidden
PROP_HIDE_ROOF = "charon_station_hide_%s_roof"


def _set_shown(objects, shown):
    for obj in objects:
        obj.hide_set(not shown)
        obj.hide_render = not shown


def part_objects(part):
    """A part's objects, less its build zones."""
    collection = find_station(part)
    if collection is None:
        return []
    return [obj for obj in collection.all_objects if not obj.name.endswith(_HIDDEN_SUFFIXES)]


def is_part_shown(part):
    return any(not obj.hide_get() for obj in part_objects(part))


def show_part(part, shown):
    _set_shown(part_objects(part), shown)


def station_objects():
    """Every object of every part, build zones and modules included."""
    return [obj for collection in find_stations() for obj in collection.all_objects]


def is_selectable():
    """Whether the station's pieces can be clicked on - off by default, so
    a base built inside it can be worked on without picking up the station."""
    return any(not obj.hide_select for obj in station_objects())


def set_selectable(selectable, objects=None):
    for obj in station_objects() if objects is None else objects:
        obj.hide_select = not selectable
        if not selectable and obj.select_get():
            obj.select_set(False)


def section_objects(section, roofs=None):
    """The interior's objects that make up one of its SECTIONS - only its
    roof with `roofs` True, everything but with False."""
    marker = "_%s" % section
    found = []
    for obj in part_objects(INTERIOR):
        if marker not in obj.name:
            continue
        is_roof = obj.name.endswith("%s_ROOF" % marker)
        if roofs is None or roofs == is_roof:
            found.append(obj)
    return found


def is_section_shown(section):
    return any(not obj.hide_get() for obj in section_objects(section, roofs=False))


def is_roof_hidden(section):
    collection = find_station(INTERIOR)
    return bool(collection is not None and collection.get(PROP_HIDE_ROOF % section.lower()))


def show_section(section, shown):
    """Show or hide a section - its roof comes back only if it isn't kept
    hidden."""
    _set_shown(section_objects(section, roofs=False), shown)
    _set_shown(section_objects(section, roofs=True), shown and not is_roof_hidden(section))


def hide_roof(section, hidden):
    collection = find_station(INTERIOR)
    if collection is None:
        return
    collection[PROP_HIDE_ROOF % section.lower()] = bool(hidden)
    if is_section_shown(section):
        _set_shown(section_objects(section, roofs=True), not hidden)


def frame_objects(space, objects, margin=1.1):
    """Point a 3D viewport at `objects`, near enough that they fill it -
    whether or not they are showing, and without touching the selection."""
    from mathutils import Vector

    corners = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    if not corners:
        return False
    low = Vector([min(corner[i] for corner in corners) for i in range(3)])
    high = Vector([max(corner[i] for corner in corners) for i in range(3)])
    radius = max((high - low).length / 2, 0.01)

    # the viewport's field of view, from its lens on a 36mm sensor
    angle = 2 * math.atan(36.0 / (2 * space.lens))
    view = space.region_3d
    view.view_location = (low + high) / 2
    view.view_distance = radius / math.sin(angle / 2) * margin
    extend_view_clip(max(VIEW_CLIP_END, view.view_distance + radius * 2))
    return True


# how far every 3D viewport draws once a station is in - a whole station is
# far bigger than Blender's default 1000 reaches
VIEW_CLIP_END = 100000.0


def extend_view_clip(clip_end=VIEW_CLIP_END):
    """Let every 3D viewport draw out to `clip_end`, never pulling one in
    that already reaches further."""
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type == "VIEW_3D" and space.clip_end < clip_end:
                    space.clip_end = clip_end


# Importing ---
def _relink_images(images):
    """Point images at their file in models/space_station/textures, without
    loading them - Blender reads each one when it is first drawn.

    Returns:
        int: How many have no file there.
    """
    missing = 0
    for image in images:
        if image.packed_file is not None or image.source != "FILE" or not image.filepath:
            continue
        path = os.path.join(TEXTURE_PATH, re.split(r"[\\/]", image.filepath)[-1])
        if os.path.isfile(path):
            image.filepath_raw = path
        else:
            missing += 1
    return missing


def _new(collection, before):
    return [block for block in collection if block.as_pointer() not in before]


def import_part(context, part, kind, palette_index=SAVED_PALETTE):
    """Append one part of a station into its own collection at the 3D
    cursor, its textures found and its colours set.

    Returns:
        (collection, objects, textures with no file)
    """
    path = part_path(part, kind)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    started = time.perf_counter()
    kinds = (bpy.data.images, bpy.data.materials, bpy.data.node_groups, bpy.data.meshes)
    before = [{block.as_pointer() for block in data} for data in kinds]

    # only the objects are asked for; their meshes, materials, textures and
    # node groups come with them
    with bpy.data.libraries.load(path, link=False) as (source, target):
        target.objects = list(source.objects)
    objects = [obj for obj in target.objects if obj is not None]
    appended = time.perf_counter()

    images, new_materials, groups, meshes = (_new(data, seen) for data, seen in zip(kinds, before))
    for block in images + new_materials + groups + meshes:
        block[PROP_TAG] = True
    missing = _relink_images(images)

    collection = bpy.data.collections.new(
        "Space Station %s %s" % (part.title(), kind_label(part, kind))
    )
    collection[PROP_PART] = part
    collection[PROP_KIND] = kind
    context.scene.collection.children.link(collection)
    cursor = context.scene.cursor.location.copy()
    for obj in objects:
        collection.objects.link(obj)
        if obj.parent is None:
            obj.location = obj.location + cursor
        if obj.name.endswith(_HIDDEN_SUFFIXES):
            obj.hide_set(True)
            obj.hide_render = True
    # scenery, not something to click on - see is_selectable
    set_selectable(False, objects)
    recolour(collection, palette_index)
    placed = time.perf_counter()

    # the same passes an appended part gets, over only what came in: glow,
    # the texture limit, a tint for colourable materials with no mask - then
    # one of each texture and of the colourise node group
    materials.prepare_materials(new_materials)
    materials.dedupe_appended_data()
    finished = time.perf_counter()
    print("Charon Forge: space station %s %s imported in %.2fs (append %.2fs, set up "
          "%.2fs, materials %.2fs), %d materials, %d textures"
          % (part.lower(), kind, finished - started, appended - started,
             placed - appended, finished - placed, len(new_materials), len(images)))
    return collection, objects, missing


def recolour(collection, palette_index):
    """Colour a part with a station palette - nothing is reloaded, the
    colourise node group reads the colours off the objects."""
    palette = game_data.palette(palette_index) if palette_index != SAVED_PALETTE else None
    collection[PROP_PALETTE] = int(palette_index)
    if palette is None:
        return
    for obj in collection.all_objects:
        if obj.type == "MESH":
            # the finish it was saved with stays
            apply_palette(obj, palette, obj.get(PROP_FINISH, 0))


def remove_station(collection):
    """Take a part out of the file - its objects and collection, and
    whatever its import brought in that nothing else uses now."""
    remove_objects(list(collection.all_objects), [collection])


def remove_section(section):
    """Take one of the interior's SECTIONS out - its model, floor and roof -
    or, if nothing else of the interior is left but build zones, the whole
    interior."""
    collection = find_station(INTERIOR)
    if collection is None:
        return
    going = section_objects(section)
    left = [obj for obj in part_objects(INTERIOR) if obj not in going]
    if not left:
        remove_station(collection)
    else:
        remove_objects(going)


def remove_objects(objects, extra=()):
    """Remove station objects (and `extra` datablocks, like their
    collection), then whatever the station's imports brought in that
    nothing uses now."""
    started = time.perf_counter()
    meshes = {obj.data for obj in objects if obj.data is not None}
    bpy.data.batch_remove(list(objects) + list(extra))
    bpy.data.batch_remove([mesh for mesh in meshes if mesh.users == 0])

    # removing the materials frees their textures and node groups, and a node
    # group can hold others - so again until nothing more comes free
    while True:
        unused = [block
                  for data in (bpy.data.materials, bpy.data.node_groups, bpy.data.images)
                  for block in data if block.get(PROP_TAG) and block.users == 0]
        if not unused:
            break
        bpy.data.batch_remove(unused)
    print("Charon Forge: space station part removed in %.2fs" % (time.perf_counter() - started))
