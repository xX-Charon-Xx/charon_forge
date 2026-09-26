"""Designing a space station's exterior by hand instead of from a seed.

The game builds a station's exterior by walking its descriptor tree
(utils/seed_utils.py): a body (_TYPE_), then each group under it - what sits
on top, underneath, at the arms' ends, a ring - each option placing modules
around the body. Here every one of those choices is a setting, read out of
the same tree so it can't go out of step with the data, and handed to
seed_utils as forced picks: the station is exactly what was chosen.

The settings live on the scene (scene.charon_station_design), so a design
is still there the next time the station popup opens. What the tree leaves
to chance inside a module, and the hull's colours, come from the chosen
hull colour preset's seed.
"""

import json

import bpy
from bpy.props import BoolProperty, EnumProperty

from ..utils import seed_utils
from . import station_colours
from .station_library import EXTERIOR, kind_label

TYPE_GROUP = seed_utils.TYPE_GROUP

# on each part's collection of a station built from a design, so the
# popup reopens on the Design tab
PROP_DESIGNED = "charon_station_designed"
# on the same collections: what they were built from (design_key), so the
# same design again only needs recolouring
PROP_DESIGN_KEY = "charon_station_design_key"

# what each group is, and what its options are called - the tree names them
# only by abbreviations
GROUP_LABELS = {
    "_TSTRING_": "Ring", "_OSTRING_": "Rings",
    "_TBS_": "Top Module", "_OBS_": "Top Module",
    "_TSTB_": "Under Modules", "_OSTB_": "Under Modules",
    "_DEND_": "Arm Ends", "_XEND_": "Arm Ends", "_TEND_": "Arm Ends",
    "_DLOW_": "Lower Module", "_DLAYOUT_": "Top", "_DTOP_": "Top Module",
    "_DRING_": "Ring", "_DRTYPE_": "Ring Type",
    "_XFEATURE_": "Arm Modules", "_TFEATURE_": "Arm Modules",
    "_XFMB_": "Lower Modules", "_TFMB_": "Lower Modules",
    "_XFMT_": "Upper Modules", "_TFMT_": "Upper Modules",
    "_TOPOO_": "Top Base", "_TSFEATURE_": "Top Module",
}
OPTION_LABELS = {
    "S": "Sphere", "P": "Prism", "ST": "Storage", "T": "Tower",
    "SPHERE": "Sphere", "PRISM": "Prism", "STORAGE": "Storage", "TOWER": "Tower",
    "ON": "On", "FEET": "Feet", "CLASPS": "Clasps", "CLASPTRI": "Triangle Clasps",
    "CTRI": "Triangle Clasps", "MIX": "Mixed", "RING": "Full", "RP": "Partial",
    "TND": "Module", "TDISKXRARE": "Second Disk (Rare)", "TRIANGLEREF": "On",
}
# option names that mean nothing goes there - the tree has several of each,
# to weight the draw, which are one choice here
_NOTHING = ("NONE", "TOPNONE", "UNDERNONE", "TRNONE", "OFF")

# the switches of the hull's paint layers (seed_utils' data), and their names
HULL_DETAILS = (
    ("nms_tex_LARGETILING1_PAINTED", "Painted", "The painted panels"),
    ("nms_tex_LARGETILING1_ALTPANELS", "Alt Panels", "The alternate panels"),
    ("nms_tex_LARGETILING1_ACCENTPANELS", "Accents", "The accent panels"),
    ("nms_tex_LARGETILING1ALT_MAINCOLOUR", "Main Colour", "The main colour"),
    ("nms_tex_LARGETILING1ALT_COLPANELS", "Colour Panels", "The coloured panels"),
    ("nms_tex_LARGETILING1ALT_STRIPES", "Stripes", "The stripes"),
)

# the hull colour presets: seeds whose palettes the game would give a system
HULL_PRESETS = 24


class _Group:
    """One choice of the design: a descriptor group and its options."""

    def __init__(self, group, options):
        self.group = group
        self.prop = "g" + group.strip("_").lower()
        self.label = GROUP_LABELS.get(group, group.strip("_").title())
        self.items, self.children, seen_nothing = [], {}, None
        # the common options first - the first is the default
        ordered = sorted(options, key=lambda option: -option[1])
        for option_id, weight, child_lists, _refs in ordered:
            if weight <= 0:
                continue
            suffix = option_id[len(group):] if option_id.startswith(group) else option_id
            if suffix.rstrip("0123456789") in _NOTHING:
                if seen_nothing is not None:
                    continue
                seen_nothing = option_id
                label = "None"
            else:
                label = OPTION_LABELS.get(suffix, suffix.title())
            self.items.append((option_id, label, "%s: %s" % (self.label, label)))
            self.children[option_id] = _groups(child_lists)


def _groups(child_lists):
    """The choices under an option - a group with one option isn't one, but
    what's under it still is."""
    out = []
    for groups in child_lists:
        for group, options in groups:
            choice = _Group(group, options)
            if len(choice.items) > 1:
                out.append(choice)
            else:
                for children in choice.children.values():
                    out.extend(children)
    return out


_bodies = None


def bodies():
    """[(body option id, label, [its choices])], read from the tree once."""
    global _bodies
    if _bodies is None:
        data = seed_utils._load()
        _bodies = []
        for group, options in seed_utils._all_groups(data.tree[data.exterior]):
            if group != TYPE_GROUP:
                continue
            for option_id, _weight, child_lists, _refs in options:
                kind = option_id.rsplit("_", 1)[-1]
                _bodies.append((option_id, kind_label(EXTERIOR, kind), _groups(child_lists)))
    return _bodies


def _all_choices():
    seen = {}
    for _body, _label, groups in bodies():
        stack = list(groups)
        while stack:
            choice = stack.pop()
            seen.setdefault(choice.prop, choice)
            for children in choice.children.values():
                stack.extend(children)
    return list(seen.values())


def visible(design):
    """[(depth, choice)] the chosen body has, following each pick into what
    it opens up."""
    body = next((b for b in bodies() if b[0] == design.body), None)
    out = []

    def walk(choices, depth):
        for choice in choices:
            out.append((depth, choice))
            walk(choice.children.get(getattr(design, choice.prop), []), depth + 1)

    if body is not None:
        walk(body[2], 0)
    return out


def force(design):
    """{group: option id} of the design, for seed_utils."""
    picks = {TYPE_GROUP: design.body}
    for _depth, choice in visible(design):
        picks[choice.group] = getattr(design, choice.prop)
    return picks


def design_key(design, use_interior, use_exterior, interior):
    """Everything a build depends on, as text: two builds with the same key
    make the same station, bar the interior's colours."""
    return json.dumps({
        "interior": interior if use_interior else None,
        "exterior": force(design) if use_exterior else None,
        "modules": bool(design.use_modules) and use_exterior,
        "hull": design.hull_colours,
        "layers": hull_layers(design),
    }, sort_keys=True)


def exterior_kind(design):
    return design.body.rsplit("_", 1)[-1]


def hull_layers(design):
    """{layer switch: 0 or 1} of the hull details chosen."""
    return {switch: int(getattr(design, detail_prop(switch))) for switch, _l, _d in HULL_DETAILS}


def detail_prop(switch):
    return "hull_" + switch.rsplit("_", 1)[-1].lower()


def hull_seed(index):
    """The seed of hull colour preset `index`."""
    return seed_utils._fmix(0x5EED + int(index)) & seed_utils.SEED_MASK


_hull_items = []


def _hull_items_of(self, context):
    """The hull colour presets, each named after and showing its colours."""
    global _hull_items
    if not _hull_items:
        for index in range(HULL_PRESETS):
            tints = seed_utils.layer_colours(seed_utils.station_palettes(hull_seed(index)))
            shown = [tints[layer] for layer in (
                "LARGETILING1_PAINTED", "LARGETILING1ALT_MAINCOLOUR",
                "LARGETILING1_ALTPANELS", "LARGETILING1_ACCENTPANELS")]
            _hull_items.append((
                str(index),
                "%d  %s" % (index + 1, station_colours.colours_name(shown)),
                "Hull colours: %s" % station_colours.hex_colours(shown),
                station_colours.swatch_icon("hull%d" % index, shown),
                index,
            ))
    return _hull_items


def _body_items(self, context):
    return [(body, label, "A %s body" % label.lower()) for body, label, _g in bodies()]


def _make_design_class():
    """The settings class, one enum per choice in the tree."""
    annotations = {
        "body": EnumProperty(name="Body", description="The station's body",
                             items=_body_items),
        "use_modules": BoolProperty(
            name="Modules", default=True,
            description="The modules the design puts around the body"),
        "hull_colours": EnumProperty(
            name="Hull Colours", description="The colours of the station's hull",
            items=_hull_items_of),
    }
    for choice in _all_choices():
        annotations[choice.prop] = EnumProperty(
            name=choice.label, description="The station's %s" % choice.label.lower(),
            items=choice.items)
    for switch, label, description in HULL_DETAILS:
        annotations[detail_prop(switch)] = BoolProperty(
            name=label, description="Show the hull's %s" % description.lower(),
            default=bool(seed_utils._load().switches.get(switch, 1)))
    return type("CharonStationDesign", (bpy.types.PropertyGroup,),
                {"__annotations__": annotations})


StationDesign = None


def register():
    global StationDesign
    StationDesign = _make_design_class()
    bpy.utils.register_class(StationDesign)
    bpy.types.Scene.charon_station_design = bpy.props.PointerProperty(type=StationDesign)


def unregister():
    global StationDesign
    del bpy.types.Scene.charon_station_design
    bpy.utils.unregister_class(StationDesign)
    StationDesign = None
