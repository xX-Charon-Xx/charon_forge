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

A station built from a galactic address opens here too, the design set to
its picks (load_address): what the tree leaves to chance then stays the
address's, the hull can keep its system's own colours (SYSTEM_HULL), and
once it differs from what the address builds the popup offers a reset.
"""

import json

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from ..utils import seed_utils
from . import station_colours, station_library
from .station_library import EXTERIOR, kind_label

TYPE_GROUP = seed_utils.TYPE_GROUP

# on each part's collection of a station built from a design, so the
# popup reopens on the Design tab
PROP_DESIGNED = "charon_station_designed"
# on the same collections: what they were built from (design_key), so the
# popup reopens on that design
PROP_DESIGN_KEY = "charon_station_design_key"
# on the same collections of a station built from a galactic address: its
# system seed, kept while the station is changed in the Design tab - and
# whether it now differs from what the address builds, which offers a reset
PROP_ADDRESS = "charon_station_address"
PROP_MODIFIED = "charon_station_modified"

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
# the hull colours item of a station from an address: its system's own
SYSTEM_HULL = "SYSTEM"


class _Group:
    """One choice of the design: a descriptor group and its options."""

    def __init__(self, group, options):
        self.group = group
        self.prop = "g" + group.strip("_").lower()
        self.label = GROUP_LABELS.get(group, group.strip("_").title())
        self.options = [option[0] for option in options]
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
        self.nothing = seen_nothing

    def item_for(self, chosen):
        """The item standing for this group's pick in a set of picked
        options - its None for any of its nothing options - or None if the
        group wasn't picked from."""
        picked = next((option for option in self.options
                       if seed_utils._chosen_name(option) in chosen), None)
        if picked is None:
            return None
        if any(item[0] == picked for item in self.items):
            return picked
        return self.nothing


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


def design_key(design, use_interior, use_exterior):
    """Everything a build depends on, as text: two builds with the same key
    make the same station, bar the interior's colours."""
    return json.dumps({
        "interior": design.interior if use_interior else None,
        "exterior": force(design) if use_exterior else None,
        "modules": bool(design.use_modules) and use_exterior,
        "hull": design.hull_colours,
        "layers": hull_layers(design),
        "address": design.address,
    }, sort_keys=True)


def load_key(design, key):
    """Set the design back to the one a design_key() was made from."""
    try:
        built = json.loads(key)
    except ValueError:
        return
    design.address = built.get("address", "")
    picks = built.get("exterior") or {}
    set_choice(design, "body", picks.get(TYPE_GROUP))
    for choice in _all_choices():
        set_choice(design, choice.prop, picks.get(choice.group))
    set_choice(design, "interior", built.get("interior"))
    if built.get("exterior") is not None:
        design.use_modules = bool(built.get("modules", True))
    set_choice(design, "hull_colours", built.get("hull"))
    for switch, value in (built.get("layers") or {}).items():
        set_choice(design, detail_prop(switch), bool(value))


def load_address(design, config):
    """Set the design to the station a galactic address builds (a
    seed_utils.station_config()): its picks, its system's own hull colours
    and the hull details the game shows by default."""
    chosen = set(config["choices"])
    design.address = "0x%X" % config["seed"]
    set_choice(design, "body", next((body for body, _label, _groups in bodies()
                                     if body.rsplit("_", 1)[-1] == config["exterior"]), None))
    for choice in _all_choices():
        set_choice(design, choice.prop, choice.item_for(chosen))
    set_choice(design, "interior", config["interior"])
    design.use_modules = True
    design.hull_colours = SYSTEM_HULL
    for switch, value in default_layers().items():
        setattr(design, detail_prop(switch), bool(value))


def set_choice(design, prop, value):
    # a value the enum doesn't have (the tree changed, or another body's
    # group of the same name) leaves it as it is
    if value is None:
        return
    try:
        setattr(design, prop, value)
    except (TypeError, AttributeError):
        pass


def address_seed(design):
    """The system seed of the address the design changes, or None."""
    return seed_utils.parse_seed(design.address) if design.address else None


def shape_seed(design):
    """The seed a build draws what the design leaves to chance from: the
    address's, so what wasn't changed stays as it was - else the hull
    preset's."""
    address = address_seed(design)
    return address if address is not None else hull_seed(_preset(design))


def palette_seed(design):
    """The seed whose palettes colour the hull."""
    if design.hull_colours == SYSTEM_HULL and design.address:
        return address_seed(design)
    return hull_seed(_preset(design))


def _preset(design):
    # SYSTEM_HULL - or nothing, once the address it stood for is gone
    return int(design.hull_colours) if design.hull_colours.isdigit() else 0


def clear_address(design):
    """Make the design one from scratch, changing no address's station."""
    design.address = ""
    if not design.hull_colours.isdigit():
        design.hull_colours = "0"


def station_address():
    """The system seed of the galactic address the station in the file was
    built from - kept while it is changed in the Design tab - or None."""
    stations = station_library.find_stations()
    for collection in stations:
        if PROP_ADDRESS in collection:
            return seed_utils.parse_seed(collection[PROP_ADDRESS])
    # built from an address before it was kept on its own
    for collection in stations:
        if seed_utils.PROP_SEED in collection and not collection.get(PROP_DESIGNED):
            return seed_utils.parse_seed(collection[seed_utils.PROP_SEED])
    return None


def station_modified():
    """Whether the station in the file was changed from what its address
    builds."""
    return any(collection.get(PROP_MODIFIED) for collection in station_library.find_stations())


def is_modified(design, config, palette, use_exterior):
    """Whether a build of the design (its station_config(), interior
    palette) differs from what its address builds - by its shape, any
    module, or its colours."""
    address = seed_utils.station_config(address_seed(design))

    def shape(built):
        return (built["interior"], built["exterior"],
                sorted((module["slot"], module["file"]) for module in built["modules"]))

    return (shape(config) != shape(address) or palette != station_library.SAVED_PALETTE
            or design.hull_colours != SYSTEM_HULL or hull_layers(design) != default_layers()
            or (use_exterior and not design.use_modules))


def exterior_kind(design):
    return design.body.rsplit("_", 1)[-1]


def hull_layers(design):
    """{layer switch: 0 or 1} of the hull details chosen."""
    return {switch: int(getattr(design, detail_prop(switch))) for switch, _l, _d in HULL_DETAILS}


def default_layers():
    """hull_layers() of the details the game shows by default."""
    switches = seed_utils._load().switches
    return {switch: int(bool(switches.get(switch, 1))) for switch, _l, _d in HULL_DETAILS}


def detail_prop(switch):
    return "hull_" + switch.rsplit("_", 1)[-1].lower()


def hull_seed(index):
    """The seed of hull colour preset `index`."""
    return seed_utils._fmix(0x5EED + int(index)) & seed_utils.SEED_MASK


def _hull_item(key, name, seed, value, icon):
    """An enum item named after and showing the hull colours of a seed."""
    tints = seed_utils.layer_colours(seed_utils.station_palettes(seed))
    shown = [tints[layer] for layer in (
        "LARGETILING1_PAINTED", "LARGETILING1ALT_MAINCOLOUR",
        "LARGETILING1_ALTPANELS", "LARGETILING1_ACCENTPANELS")]
    return (key, "%s  %s" % (name, station_colours.colours_name(shown)),
            "Hull colours: %s" % station_colours.hex_colours(shown),
            station_colours.swatch_icon(icon, shown), value)


_hull_items = []
# the presets and then an address's own colours, for a design changing it
_address_items = [None, []]


def _hull_items_of(self, context):
    """The hull colour presets - and a design changing a station built from
    an address, that system's own colours. Blender needs the list kept alive
    while it shows it."""
    global _hull_items
    if not _hull_items:
        _hull_items = [_hull_item(str(index), str(index + 1), hull_seed(index), index,
                                  "hull%d" % index)
                       for index in range(HULL_PRESETS)]
    if not self.address:
        return _hull_items
    if _address_items[0] != self.address:
        system = _hull_item(SYSTEM_HULL, "System's Own", seed_utils.parse_seed(self.address),
                            HULL_PRESETS, "hull" + self.address)
        _address_items[:] = [self.address, [system] + _hull_items]
    return _address_items[1]


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
        "interior": EnumProperty(
            name="Interior", description="Which space station interior",
            items=station_library.INTERIORS),
        "interior_colours": EnumProperty(
            name="Interior Colours", description="The station palette to colour it with",
            items=station_library.palette_items),
        # the galactic address (0x hex system seed) of the station the design
        # changes - empty for a station designed from scratch
        "address": StringProperty(options={"HIDDEN"}),
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
