"""Space stations from a system seed, out of the parts in models/space_station.

Give it a system's seed and it builds that system's station the way the game
does: the same shape, the same modules around it, the same colours. Everything
here is ported from the planet seed research (The Augur,
docs/research/SEED_KNOWLEDGE.md, "Space station shape" and "Station colours"),
which runs the game's own code:

Shape. The station's seed is the first child seed of an RNG on the system seed.
The game walks the station's descriptor tree from SPACESTATIONTYPEB: per group
one weighted pick (weight 20, 1 for an xRARE option, 0 for xNEVER), then a
child seed for each child group list of the picked option and one for each
scene it references, each walked with its own RNG. Every picked name goes into
one set, and a group with an option already in it is skipped - that is how the
hangar inherits the entrance's launch tube, and why every tower of a station is
the same tower. The research's port of this walk matches the exe on 3000 of
3000 systems; resources/station_seed.json holds its data.

    interior/STATION_INTERIOR_<TUBE>.blend    the launch tube (_TUBE_)
    exterior/STATION_EXTERIOR_<TYPE>.blend    the body (_TYPE_)
    exterior/modules/STATION_MODULE_*.blend   every module slot the picks show
                                              (module slots, from the station
                                              library's stations.json), each
                                              the module variant picked

Colours. The station's palettes come from the ordinary palette generator run on
the SYSTEM seed with the base palettes (biome 16), not from any planet; checked
against two docked stations. The hull's textures (LARGETILING1, LARGETILING1ALT)
are stacks of layers, each tinted from one palette at one of its five colours
(TkPaletteTexture ColourAlt: Primary = colour 0, Alternative1 = 1, ...):

    BASE          Metal (9)             Primary         always
    PAINTED       SpaceStationBase (60) Primary         always     LARGETILING1
    ALTPANELS     SpaceStationBase      Alternative1    70 %
    ACCENTPANELS  SpaceStationAlt (61)  Alternative1    70 %
    MAINCOLOUR    SpaceStationAlt       Alternative2    always     LARGETILING1ALT
    COLPANELS     SpaceStationBase      Alternative1    40 %
    STRIPES       SpaceStationAlt       Primary         50 %, one of 4

The palette colours are exact. Three things are not predicted, because the
game rolls them per texture instance (TkPaletteTexture Index -1, layer
Probability): which of its palette's five colours a layer shows - ColourAlt
is the default here, but a docked station has shown other colours of the
same palette, so each layer's colour can be chosen (build_station's
`colours`); whether a layer with a chance below 100 % shows (here every layer
at 50 % or more, the data's switches); and how a colour goes onto a layer (the
layers are Multiply = false with an AverageColour, so the layer's average is
shifted onto the palette colour, keeping its detail - see tint_materials).
The layer textures are tint masks the extraction left untinted, which is why
an untinted hull is teal.

What the files cannot follow: the body and interior files were built with one
set of their inner choices (the core's skin _TS_, the arms' connectors _CTYPE_,
the tunnel opening _TOTYPE_, the front panel style _STYLE_, the hangar window,
the trade hall's props), so a station whose seed picks others differs there.
build_station() reports each such choice (config["baked"]). The interior's
base-building pieces keep the colours they were saved with unless a STATIONBASE
palette is given (station_library.recolour).

Frame: every file's object sits at the origin turned +90 degrees about X, its
mesh in the game's metres. A module at a slot goes to cursor @ Rx(+90) @ slot
matrix - the frame the body and the interior share.
"""

import json
import math
import os
import random
import re
import struct
import time

import bpy
import mathutils

from .. import materials
from ..builder import station_library
from ..utils import collection_utils

# the game data this runs on: the station's descriptor tree, its palettes, the
# module slots and the hull's layers (see _Data)
DATA_PATH = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "..", "resources", "station_seed.json"))
MODULE_PATH = os.path.join(station_library.STATION_PATH, "exterior", "modules")
MODULE_PREFIX = "STATION_MODULE_"

TUBE_GROUP = "_TUBE_"
TYPE_GROUP = "_TYPE_"

# on each part's collection: the system seed and what it picked
PROP_SEED = "charon_station_seed"
PROP_CHOICES = "charon_station_choices"
# on each module object: which slot it fills, and the module file it is
PROP_SLOT = "charon_station_slot"
PROP_MODULE = "charon_station_module"
# on every station object: each hull layer's colour, linear RGB + 1 (see
# tint_materials)
PROP_COLOUR = "nms_sta_%s"
# on a material once its layers are tinted
PROP_TINTED = "charon_station_tinted"

M32 = 0xFFFFFFFF
M64 = 0xFFFFFFFFFFFFFFFF
SEED_MASK = 0xFFFFFFFFFFFFF     # the game uses the low 52 bits of a system seed


# Data ---
class _Data:
    """resources/station_seed.json, read into the shapes the logic walks:

        scene_root, root, exterior   scene names (tree keys are under
                                     scene_root, without .SCENE.MBIN)
        tree         {scene: [(group, [(id, weight, [child group lists],
                     [referenced scenes])])]} - a None reference is a scene
                     with no descriptor, which still takes a child seed
        tables       {slot: (mode, [64 sRGB colours])}, the base palettes
        names        {slot: palette name}
        dedupe       how close two picked colours may be
        scenes       the scene at each module slot, by slot index
        slots        [(scene index, owners, first three matrix rows)]
        layers       {hull layer: (palette slot, colour 0..4)}
        textures     {layer texture stem: hull layer}
        switches     {layer switch: value shown by default}
        race_groups  the trade hall's prop groups the game swaps for the
                     system's race
    """

    def __init__(self, raw):
        def groups(entries):
            return [(g["group"], [(o["id"], o["weight"],
                                   [groups(c) for c in o.get("children", [])],
                                   list(o.get("refs", [])))
                                  for o in g["options"]])
                    for g in entries]

        self.scene_root = raw["scene_root"]
        self.root = raw["root"]
        self.exterior = raw["exterior"]
        self.tree = {scene: groups(entries) for scene, entries in raw["tree"].items()}
        palettes = raw["palettes"]
        self.tables = {int(slot): (t["mode"], [tuple(c) for c in t["colours"]])
                       for slot, t in palettes["tables"].items()}
        self.names = {int(slot): name for slot, name in palettes["names"].items()}
        self.dedupe = palettes["dedupe"]
        self.scenes = list(raw["modules"]["scenes"])
        self.slots = [(s["scene"], tuple(s["owners"]), tuple(s["matrix"]))
                      for s in raw["modules"]["slots"]]
        hull = raw["hull"]
        self.layers = {k: (v["palette"], v["colour"]) for k, v in hull["layers"].items()}
        self.textures = dict(hull["textures"])
        self.switches = dict(hull["switches"])
        self.race_groups = tuple(raw["race_groups"])


_data = None


def _load():
    """The data, read once."""
    global _data
    if _data is None:
        with open(DATA_PATH, "r", encoding="utf-8") as handle:
            _data = _Data(json.load(handle))
    return _data


# Seeds ---
def parse_seed(value):
    """An int from an int, a decimal string or a 0x hex string (the way the
    game and The Augur print seeds). None or "" gives a random one."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return random_seed()
    if isinstance(value, int):
        return value & M64
    text = str(value).strip().lower()
    return int(text, 16 if text.startswith("0x") else 10) & M64


def random_seed():
    return random.getrandbits(52)


# The game's RNG (research tools/pack_reference.py, Rng) ---
def _fmix(v):
    v &= M64
    v ^= v >> 33
    v = (v * 0x64DD81482CBD31D7) & M64
    v ^= v >> 33
    v = (v * 0xE36AA5C613612997) & M64
    v ^= v >> 33
    return v


def _f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


class Rng:
    K = 0x5A76F899

    def __init__(self, seed=0, a=None, b=None):
        if a is not None:
            self.a, self.b = a, b
            return
        lo, hi = seed & M32, (seed >> 32) & M32
        self.a = (lo + (lo == 0)) & M32
        self.b = (((lo >> 16) | (lo << 16)) & M32) ^ hi ^ lo

    def copy(self):
        return Rng(a=self.a, b=self.b)

    def step(self):
        t = self.a * self.K + self.b
        self.a, self.b = t & M32, t >> 32
        return self.a

    def uint(self, n):
        return (self.step() * n) >> 32

    def child_seed(self):
        a1 = self.step()
        a2 = self.step()
        return _fmix((a2 << 32) | a1)


# Addresses ---
def split_address(address):
    """The fields of a galactic address as a save stores it (a base's
    GalacticAddress, int or 0x hex string):

        bits 52..55  planet index (0 for a base in space)
        bits 40..51  solar system index
        bits 32..39  galaxy (0 = Euclid)
        bits 24..31  voxel Y
        bits 12..23  voxel Z
        bits  0..11  voxel X

    The low 52 bits are the system seed (research: portal address ->
    system seed, verified on the Euclid bases of a save)."""
    address = parse_seed(address)
    return {
        "planet": (address >> 52) & 0xF,
        "system_index": (address >> 40) & 0xFFF,
        "galaxy": (address >> 32) & 0xFF,
        "y": (address >> 24) & 0xFF,
        "z": (address >> 12) & 0xFFF,
        "x": address & 0xFFF,
        "system_seed": address & SEED_MASK,
    }


def parse_address(text):
    """A galactic address typed in by hand, as a save's GalacticAddress:

        0x40050003AB8C07     a save's address, hex (or decimal)
        40050003AB8C         12 hex digits: portal glyphs, PSSSYYZZZXXX -
                             the same fields less the galaxy, so Euclid

    Spaces and dashes are ignored. Raises ValueError on anything else."""
    text = re.sub(r"[\s\-_]", "", str(text or ""))
    if not text:
        raise ValueError("no address")
    if re.fullmatch(r"[0-9A-Fa-f]{12}", text):
        glyphs = int(text, 16)
        # the glyphs' planet and system sit above the galaxy byte a save has
        return ((glyphs >> 32) << 40) | (glyphs & 0xFFFFFFFF)
    return parse_seed(text)


def system_seed_from_address(address):
    """The system seed of a save's galactic address: its low 52 bits."""
    return parse_seed(address) & SEED_MASK


def station_seed(system_seed):
    """The seed the game builds a system's station from: the first child
    seed of an RNG on the system seed (exe 0x14163f8b0, cGcSpaceStationSpawnData
    Seed)."""
    return Rng(parse_seed(system_seed) & SEED_MASK).child_seed()


def station_seed_from_address(address):
    """The station seed of a save's galactic address, e.g. a
    PlayerSpaceStationBase's GalacticAddress:

        station_seed_from_address(0xFFFF446729A4) == 0x0C63D2AB104B20D6
    """
    return station_seed(system_seed_from_address(address))


# Shape ---
def _chosen_name(option_id):
    """The name the game records: an id ending in LOD<digit> loses it."""
    i = option_id.find("LOD")
    if i >= 0 and len(option_id) - i == 4 and option_id[i + 3].isdigit():
        return option_id[:i].upper()
    return option_id


def station_choices(system_seed, force=None):
    """Every descriptor option the game picks for a system's station, in the
    order picked (upper case). `force` ({group: option id}) makes a group take
    that option instead - the draw is still made, so everything else stays
    the seed's."""
    force = {k.upper(): v.upper() for k, v in (force or {}).items()}
    tree = _load().tree
    chosen, seen = [], set()

    def walk(groups, seed):
        rng = Rng(seed)
        for group, options in groups:
            total = sum(o[1] for o in options)
            if total == 0 or any(o[0] in seen for o in options):
                continue
            r, acc, pick = rng.uint(total), 0, None
            for o in options:
                if acc <= r < acc + o[1]:
                    pick = o
                    break
                acc += o[1]
            want = force.get(group)
            if want:
                pick = next((o for o in options if o[0] == want), pick)
            if pick is None:
                continue
            name = _chosen_name(pick[0])
            if name not in seen:
                chosen.append(name)
                seen.add(name)
            for children in pick[2]:
                walk(children, rng.child_seed())
            for ref in pick[3]:
                seed = rng.child_seed()
                if ref is not None:
                    walk(tree[ref], seed)

    walk(tree[_load().root], station_seed(system_seed))
    return chosen


def _all_groups(groups):
    for group, options in groups:
        yield group, options
        for o in options:
            for children in o[2]:
                yield from _all_groups(children)


def _option_for(scene, group, kind):
    """The option of `group` in `scene` whose id ends in `kind` (ROUND, OCT)."""
    for g, options in _all_groups(_load().tree[scene]):
        if g == group:
            for o in options:
                if o[0].rsplit("_", 1)[-1] == kind.upper():
                    return o[0]
    raise ValueError("%s has no option %s" % (group, kind))


def _picked(groups, chosen):
    """[(group, option, has a choice)] of a scene's tree under the chosen set,
    in tree order, following each picked option into its children."""
    out = []
    for group, options in groups:
        pick = next((o for o in options if o[0] in chosen), None)
        if pick is None:
            continue
        out.append((group, pick[0], len(options) > 1))
        for children in pick[2]:
            out.extend(_picked(children, chosen))
    return out


def module_file(scene, chosen):
    """The module file for a module scene: its name, then each pick of a
    group with a choice (STATION_MODULE_PRISM_ACC_ARMS_END_CLASP)."""
    picks = _picked(_load().tree.get(scene, ()), chosen)
    stem = scene.rsplit("/", 1)[-1].upper()
    return MODULE_PREFIX + stem + "".join(
        "_" + option.strip("_") for _, option, choice in picks if choice)


# Colours ---

def _remap(mode, idx):
    r8 = idx % 8
    if mode == 1:
        return 0
    if mode == 2:
        return ((idx // 32) * 8 + r8 // 4) * 4
    if mode == 3:
        return r8
    if mode == 4:
        return ((idx // 16) * 8 + r8 // 2) * 2
    return idx


def _pick_palette(slot, rng):
    """The five colours of one palette (research pick_palette): two draws per
    colour, a colour too close to one already picked moves on."""
    data = _load()
    mode, colours = data.tables[slot]
    out = []
    for _ in range(5):
        c1 = rng.step() >> 29
        c2 = rng.step() >> 29
        if mode == 1:
            idx = 0
        elif mode == 2:
            idx = (((c1 >> 2) << 3) + (c2 >> 2)) << 2
        elif mode == 3:
            idx = c2
        elif mode == 4:
            idx = (((c1 >> 1) << 3) + (c2 >> 1)) << 1
        else:
            idx = (c1 << 3) + c2
        colour = colours[_remap(mode, idx)]
        for _ in range(64):
            if not any(_f32(sum((a - b) ** 2 for a, b in zip(colour, o))) < data.dedupe for o in out):
                break
            idx = (idx + 1) % 64
            colour = colours[_remap(mode, idx)]
        out.append(colour)
    return out


def _skip_palette(rng):
    for _ in range(10):
        rng.step()


def station_palettes(system_seed):
    """{slot: five sRGB colours} of the station's palettes (named in the data):
    the palette generator on the system seed, every slot before the ones
    wanted only stepping the RNG (research palettes(), biome 16)."""
    tables = _load().tables
    seed = system_seed & SEED_MASK
    root = Rng(seed)
    for _ in range(2):
        root.child_seed()
    rng = Rng(root.child_seed())            # child seed 2
    st = Rng(rng.child_seed())
    out, saved = {}, None
    for i in range(52):
        if i == 10:
            saved = st.copy()
        if i in tables:
            out[i] = _pick_palette(i, st)
        else:
            _skip_palette(st)
    tmp = st.copy()
    tmp.child_seed()
    sb = Rng(tmp.child_seed())
    _skip_palette(sb)                       # slot 51
    tail = Rng(sb.child_seed())
    for i in range(52, 66):
        source = saved if i == 56 else tail
        if i in tables:
            out[i] = _pick_palette(i, source)
        else:
            _skip_palette(source)
    return out


def hex_colour(colour):
    return "#%02X%02X%02X" % tuple(int(round(min(max(c, 0.0), 1.0) * 255)) for c in colour[:3])


# Config ---
def station_config(seed=None, interior=None, exterior=None, palette_index=None, force=None):
    """Everything a system seed makes, without touching the scene.

    seed           the system seed: int, decimal or 0x hex string, or a
                   save's GalacticAddress (its planet bits are ignored);
                   None = a random one
    interior       force the launch tube: ROUND, SQUARE or TRI
    exterior       force the body: TET, OCT, DISK, EX, TRI or SIMPLE
    palette_index  a STATIONBASE palette for the interior's base-building
                   pieces (None keeps the colours they were saved with)
    force          {group: option id} for any other choices - a station
                   designed by hand (builder/station_design.py)

    Returns a dict:
        seed, interior, exterior
        choices    every option the game picks (upper case)
        palettes   {slot: five sRGB colours} - named in the data
        palette    the STATIONBASE palette index, or SAVED_PALETTE
        modules    [{"slot", "file", "scene", "matrix"}] - the slot's 4x4
                   in the station's frame, row by row
    """
    data = _load()
    seed = system_seed_from_address(parse_seed(seed))
    force = dict(force or {})
    if interior:
        force[TUBE_GROUP] = _option_for(data.root, TUBE_GROUP, interior)
    if exterior:
        force[TYPE_GROUP] = _option_for(data.exterior, TYPE_GROUP, exterior)
    choices = station_choices(seed, force)
    chosen = set(choices)

    def kind(scene, group):
        return next(o for g, o, _ in _picked(data.tree[scene], chosen)
                    if g == group).rsplit("_", 1)[-1]

    return {
        "seed": seed,
        "interior": kind(data.root, TUBE_GROUP),
        "exterior": kind(data.exterior, TYPE_GROUP),
        "choices": choices,
        "palettes": station_palettes(seed),
        "palette": station_library.SAVED_PALETTE if palette_index is None else int(palette_index),
        "modules": station_modules(chosen),
    }


def station_modules(chosen):
    """[{"slot", "file", "scene", "matrix"}] of the module slots a set of
    picked options fills - see station_config."""
    data = _load()
    modules = []
    for slot, (index, owners, rows) in enumerate(data.slots):
        if not all(owner in chosen for owner in owners):
            continue
        scene = data.scenes[index]
        modules.append({
            "slot": slot,
            "file": module_file(scene, chosen),
            "scene": data.scene_root + scene,
            "matrix": [list(rows[0:4]), list(rows[4:8]), list(rows[8:12]),
                       [0.0, 0.0, 0.0, 1.0]],
        })
    return modules


def describe(config):
    """A few lines saying what a station_config() holds."""
    counts = {}
    for module in config["modules"]:
        counts[module["file"]] = counts.get(module["file"], 0) + 1
    lines = ["System 0x%X: %s body, %s launch tube"
             % (config["seed"], config["exterior"].title(), config["interior"].title())]
    for slot in (60, 61, 9):
        lines.append("  %-17s %s" % (_load().names[slot],
                                     " ".join(hex_colour(c) for c in config["palettes"][slot])))
    for name, count in sorted(counts.items()):
        lines.append("  %d x %s" % (count, name[len(MODULE_PREFIX):]))
    for scene, group, baked, wanted in config.get("baked", []):
        lines.append("  file has %s %s, the seed picks %s" % (group, baked, wanted))
    return "\n".join(lines)


# Materials ---
_averages = {}


def _stem(image):
    name = re.sub(r"\.\d{3}$", "", image.name)
    return re.sub(r"\.(webp|png|dds|jpg|tga)$", "", name, flags=re.I).upper()


def _linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _average(image):
    """The mean linear colour of a layer where it covers (alpha over half)."""
    key = image.name
    if key not in _averages:
        import numpy as np
        px = np.empty(len(image.pixels), np.float32)
        image.pixels.foreach_get(px)
        px = px.reshape(-1, 4)
        cover = px[:, 3] > 0.5
        rgb = px[cover, :3] if cover.any() else px[:, :3]
        if image.colorspace_settings.name.lower() in ("srgb", "srgb - texture"):
            rgb = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        _averages[key] = tuple(float(v) for v in rgb.mean(0))
    return _averages[key]


def _socket(sockets, identifier):
    return next(s for s in sockets if s.identifier == identifier)


def tint_materials(material_list):
    """Put the station palettes into every hull layer of these materials: a
    layer's colour becomes texel + (palette colour - the layer's average), so
    its average lands on the palette colour and its detail stays. The colour
    is read off the object (PROP_COLOUR), so the materials stay shared; an
    object without it keeps the untinted layer. Idempotent."""
    done = 0
    for mat in material_list:
        if mat is None or not mat.use_nodes or mat.get(PROP_TINTED):
            continue
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        for tex in [n for n in nodes if n.type == "TEX_IMAGE" and n.image]:
            layer = _load().textures.get(_stem(tex.image))
            if layer is None:
                continue
            colour = tex.outputs["Color"]
            targets = [link.to_socket for link in colour.links]
            if not targets:
                continue
            x, y = tex.location
            attr = nodes.new("ShaderNodeAttribute")
            attr.attribute_type = "OBJECT"
            attr.attribute_name = PROP_COLOUR % layer
            attr.location = (x + 300, y + 250)
            shift = nodes.new("ShaderNodeVectorMath")
            shift.operation = "SUBTRACT"
            shift.inputs[1].default_value = _average(tex.image)
            shift.location = (x + 500, y + 250)
            links.new(attr.outputs["Vector"], shift.inputs[0])
            add = nodes.new("ShaderNodeVectorMath")
            add.operation = "ADD"
            add.location = (x + 700, y + 150)
            links.new(colour, add.inputs[0])
            links.new(shift.outputs["Vector"], add.inputs[1])
            floor = nodes.new("ShaderNodeVectorMath")
            floor.operation = "MAXIMUM"
            floor.inputs[1].default_value = (0.0, 0.0, 0.0)
            floor.location = (x + 900, y + 150)
            links.new(add.outputs["Vector"], floor.inputs[0])
            # the attribute's alpha is 1 when the object has the colour
            mix = nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.location = (x + 1100, y + 150)
            links.new(attr.outputs["Alpha"], _socket(mix.inputs, "Factor_Float"))
            links.new(colour, _socket(mix.inputs, "A_Color"))
            links.new(floor.outputs["Vector"], _socket(mix.inputs, "B_Color"))
            for target in targets:
                links.new(_socket(mix.outputs, "Result_Color"), target)
            done += 1
        mat[PROP_TINTED] = True
    return done


def layer_colours(palettes, colours=None):
    """{layer: sRGB colour}: each hull layer's palette at its ColourAlt, or
    at the colour (0..4) `colours` gives it ({"LARGETILING1_PAINTED": 4})."""
    out = {}
    for layer, (slot, index) in _load().layers.items():
        index = (colours or {}).get(layer, index)
        out[layer] = palettes[slot][int(index) % 5]
    return out


def apply_colours(objects, palettes, layers=None, colours=None):
    """Write each hull layer's colour (linear) and the layer switches onto
    objects - what tint_materials' nodes read. `layers` ({switch: value})
    goes over the data's default switches, `colours` as layer_colours()."""
    switches = dict(_load().switches)
    switches.update(layers or {})
    tints = layer_colours(palettes, colours)
    for obj in objects:
        if obj.type != "MESH":
            continue
        for layer, c in tints.items():
            obj[PROP_COLOUR % layer] = [_linear(c[0]), _linear(c[1]), _linear(c[2]), 1.0]
        for name, value in switches.items():
            obj[name] = int(value)


# Building ---
# a module file's object is turned +90 degrees about X, like the body's
TURN = mathutils.Matrix.Rotation(math.pi / 2, 4, "X")


def _append_module(name):
    """Append one module file: (its object, new materials, textures with no
    file), everything it brought in tagged as the station's."""
    path = os.path.join(MODULE_PATH, name + ".blend")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    kinds = (bpy.data.images, bpy.data.materials, bpy.data.node_groups, bpy.data.meshes)
    before = [{block.as_pointer() for block in data} for data in kinds]
    with bpy.data.libraries.load(path, link=False) as (source, target):
        target.objects = list(source.objects)
    objects = [obj for obj in target.objects if obj is not None and obj.type == "MESH"]
    images, new_materials, groups, meshes = (
        [block for block in data if block.as_pointer() not in seen]
        for data, seen in zip(kinds, before))
    for block in images + new_materials + groups + meshes:
        block[station_library.PROP_TAG] = True
    missing = station_library._relink_images(images)
    # a module file holds one object; anything else would be a stray
    for extra in objects[1:]:
        bpy.data.objects.remove(extra)
    return (objects[0] if objects else None), new_materials, missing


def place_modules(context, collection, config, cursor=None):
    """Put the modules of a station_config() into `collection` (the
    exterior's), each file appended once and its mesh shared by every slot
    it fills.

    Returns:
        (objects, textures with no file)
    """
    if cursor is None:
        cursor = context.scene.cursor.location.copy()
    place = mathutils.Matrix.Translation(cursor) @ TURN
    loaded, placed, new_materials = {}, [], []
    with collection_utils.excluded_from_view_layer(collection):
        missing = _place_modules(collection, config["modules"], place, loaded, placed,
                                 new_materials)
    materials.prepare_materials(new_materials)
    return placed, missing


def _place_modules(collection, modules, place, loaded, placed, new_materials):
    """Put `modules` into the collection: a file in `loaded` ({file: object})
    is copied, anything else appended once and added to it."""
    missing = 0
    for module in modules:
        name = module["file"]
        if name not in loaded:
            obj, made, lost = _append_module(name)
            loaded[name] = obj
            new_materials += made
            missing += lost
            if obj is None:
                continue
        else:
            source = loaded[name]
            if source is None:
                continue
            obj = source.copy()                 # same mesh, own properties
        collection.objects.link(obj)
        obj.matrix_world = place @ mathutils.Matrix(module["matrix"])
        obj[PROP_SLOT] = module["slot"]
        obj[PROP_MODULE] = name
        placed.append(obj)
    return missing


def _baked(objects, chosen):
    """[(scene, group, option in the file, option the seed picks)] for every
    choice with alternatives that a file was built with and the seed does not
    pick (the files record their picks in nms_station_picks)."""
    data = _load()
    out, seen = [], set()
    for obj in objects:
        try:
            log = json.loads(obj.get("nms_station_picks", "[]"))
        except ValueError:
            continue
        for scene, picks in log:
            tree_scene = _tree_scene(scene)
            # the root's and the exterior's own choices pick the files and
            # the modules, and each module file is the variant picked
            if tree_scene in (None, data.root, data.exterior) or tree_scene in data.scenes:
                continue
            groups = {g: [o[0] for o in options]
                      for g, options in _all_groups(data.tree[tree_scene])}
            for group, option in picks:
                # the game swaps the trade hall's props for the system's race
                if group.upper() in data.race_groups:
                    continue
                options = groups.get(group.upper())
                if not options or len(options) < 2 or option.upper() in chosen:
                    continue
                wanted = next((o for o in options if o in chosen), None)
                key = (scene, group.upper())
                if wanted and key not in seen:
                    seen.add(key)
                    out.append((scene, group.upper(), option.upper(), wanted))
    return out


def _tree_scene(key):
    """A tree key from the pipeline's scene key (B_EXTERIOR_EXTCORE)."""
    for scene in _load().tree:
        stem = scene.rsplit("/", 1)[-1]
        if key.upper() in (stem, "B_EXTERIOR_" + stem, "B_DOCK_" + stem, "B_" + stem):
            return scene
    return None


def build_station(context, seed=None, interior=True, exterior=True, modules=True,
                  interior_kind=None, exterior_kind=None, palette_index=None,
                  layers=None, colours=None, replace=True, force=None):
    """Put a system's station into the scene at the 3D cursor.

    seed            the system seed, as station_config(); None = random
    interior        bring in the interior (core and runway)
    exterior        bring in the exterior body
    modules         with the exterior: the modules around it too
    interior_kind   force the launch tube (ROUND, SQUARE, TRI)
    exterior_kind   force the body (TET, OCT, DISK, EX, TRI, SIMPLE)
    palette_index   a STATIONBASE palette for the interior's base-building
                    pieces; None keeps their saved colours
    layers          {switch: value} over the data's default switches, e.g.
                    {"nms_tex_LARGETILING1ALT_COLPANELS": 1}
    colours         {layer: 0..4} - which of its palette's colours a hull
                    layer shows instead of its ColourAlt (the data's hull
                    layers)
    replace         take out the station already in the file first
    force           {group: option id} for any other choices, as
                    station_config()

    With `replace` False, the station there is changed into this one rather
    than built again - see update_station.

    Returns:
        (config, [collections], textures with no file)
    """
    config = station_config(seed, interior_kind, exterior_kind, palette_index, force)
    if replace:
        for collection in station_library.find_stations():
            station_library.remove_station(collection)
    collections, missing, _loaded = update_station(
        context, config, interior, exterior, modules, layers, colours)
    return config, collections, missing


def update_station(context, config, interior=True, exterior=True, modules=True,
                   layers=None, colours=None, palette_seed=None):
    """Make the station in the file the one a station_config() describes,
    loading only what it lacks: a part is imported again only if it is new
    or its kind changed, and a module only where its slot is new or takes
    another module - one already in the file is copied rather than loaded.
    Colours are properties on the objects, so they change in place. With no
    station in the file, it is built whole at the 3D cursor.

    interior, exterior, modules, layers, colours   as build_station()
    palette_seed    colour the hull with this system's palettes instead of
                    the config's own - a station changed by hand keeps its
                    address's seed for its shape but can take other colours

    Each part is its own collection, as station_library.import_part makes
    it (the modules go in the exterior's), so the Forge's station switches,
    recolouring and removal work on it unchanged.

    Returns:
        ([collections], textures with no file, [what was loaded, e.g.
        "exterior", "3 modules"])
    """
    started = time.perf_counter()
    if palette_seed is not None:
        config["palettes"] = station_palettes(palette_seed)
    cursor = mathutils.Vector(station_library.origin(context))
    chosen = " ".join(config["choices"])

    collections, missing, fresh, loaded = [], 0, [], []
    wanted = [(station_library.INTERIOR, interior, config["interior"]),
              (station_library.EXTERIOR, exterior, config["exterior"])]
    for part, want, kind in wanted:
        collection = station_library.find_station(part)
        if collection is not None and (not want or collection[station_library.PROP_KIND] != kind):
            station_library.remove_station(collection)
            collection = None
        if not want:
            continue
        just_made = collection is None
        if just_made:
            collection, part_objects, lost = station_library.import_part(
                context, part, kind, station_library.SAVED_PALETTE, cursor)
            missing += lost
            fresh += part_objects
            loaded.append(part.lower())
        if part == station_library.EXTERIOR:
            placed, lost, appended = _update_modules(
                collection, config["modules"] if modules else [], cursor, just_made)
            missing += lost
            fresh += placed
            if appended:
                loaded.append("%d module%s" % (appended, "" if appended == 1 else "s"))
        collection[PROP_SEED] = "0x%X" % config["seed"]
        collection[PROP_CHOICES] = chosen
        collections.append(collection)

    if loaded:
        materials.dedupe_appended_data()
    objects = [obj for collection in collections for obj in collection.all_objects]
    config["baked"] = _baked(objects, set(config["choices"]))
    # only what came in has layers still to tint - the rest already are
    tint_materials({slot.material for obj in fresh if obj.type == "MESH"
                    for slot in obj.material_slots if slot.material})
    apply_colours(objects, config["palettes"], layers, colours)
    for obj in objects:
        obj.update_tag()
    for collection in collections:
        station_library.recolour(collection, config["palette"])
    station_library.extend_view_clip()
    print("Charon Forge: %s\n  %s in %.2fs"
          % (describe(config), "loaded " + ", ".join(loaded) if loaded else "nothing loaded",
             time.perf_counter() - started))
    return collections, missing, loaded


def _update_modules(collection, modules, cursor, just_made):
    """Give the exterior's collection exactly `modules`: a slot keeping its
    module is left alone, one that is new or takes another module is filled
    - with a copy where the file already has that module, else appended -
    and one no longer wanted is taken out. A collection `just_made` is
    filled out of the view layer, as import_part fills it; one already there
    isn't, since coming back into it would show what was hidden.

    Returns:
        (objects placed, textures with no file, module files appended)
    """
    existing = {obj[PROP_SLOT]: obj for obj in collection.objects if PROP_SLOT in obj}
    # modules placed before they carried their file are known by the picks
    old_chosen = set(collection.get(PROP_CHOICES, "").split())
    old_files = {m["slot"]: m["file"] for m in station_modules(old_chosen)} if old_chosen else {}
    files = {slot: obj.get(PROP_MODULE, old_files.get(slot)) for slot, obj in existing.items()}

    wanted = {module["slot"]: module for module in modules}
    going = [obj for slot, obj in existing.items()
             if slot not in wanted or files[slot] != wanted[slot]["file"]]
    placing = [module for slot, module in wanted.items()
               if slot not in existing or files[slot] != module["file"]]
    if not going and not placing:
        return [], 0, 0
    # any module there can be copied - one on its way out too, until it goes
    loaded = {files[slot]: obj for slot, obj in existing.items() if files[slot]}
    before = len(loaded)
    hidden = bool(existing) and all(obj.hide_get() for obj in existing.values())

    place = mathutils.Matrix.Translation(cursor) @ TURN
    placed, new_materials = [], []
    if just_made:
        with collection_utils.excluded_from_view_layer(collection):
            missing = _place_modules(collection, placing, place, loaded, placed, new_materials)
    else:
        missing = _place_modules(collection, placing, place, loaded, placed, new_materials)
        for obj in placed:
            obj.hide_set(hidden)
            obj.hide_render = hidden
    materials.prepare_materials(new_materials)
    if going:
        station_library.remove_objects(going)
    print("Charon Forge: %d module(s) placed, %d taken out, %d kept"
          % (len(placed), len(going), len(existing) - len(going)))
    return placed, missing, len(loaded) - before


def find_seed():
    """The system seed of the station in the file, or None."""
    for collection in station_library.find_stations():
        if PROP_SEED in collection:
            return parse_seed(collection[PROP_SEED])
    return None


def recolour_station(seed=None, layers=None, colours=None):
    """Colour the station in the file again - with another system's palettes
    (`seed`), other layers shown or other colours per layer - without
    rebuilding it. None keeps the station's own seed.

    Returns:
        the palettes used, or None when there is no station
    """
    seed = find_seed() if seed is None else parse_seed(seed)
    if seed is None:
        return None
    palettes = station_palettes(seed)
    objects = [obj for collection in station_library.find_stations()
               for obj in collection.all_objects]
    apply_colours(objects, palettes, layers, colours)
    for obj in objects:
        obj.update_tag()
    return palettes
