"""Colours the space station decorations by tinting their painted hull tile layers
with the palette slots (nms_p / nms_s / nms_t), done once per material."""

import bpy

from .properties import COLOURISE_GROUP

# layer switch -> the palette slot property its layer shows
PAINT_LAYERS = {
    "nms_tex_LARGETILING1_PAINTED": "nms_p",
    "nms_tex_LARGETILING1_ALTPANELS": "nms_s",
    "nms_tex_LARGETILING1_ACCENTPANELS": "nms_t",
    "nms_tex_LARGETILING1ALT_MAINCOLOUR": "nms_p",
    "nms_tex_LARGETILING1ALT_COLPANELS": "nms_s",
    "nms_tex_LARGETILING1ALT_STRIPES": "nms_t",
    "nms_tex_FREIGHTER_PROC_PAINT1": "nms_p",
    "nms_tex_FREIGHTER_PROC_PAINT2": "nms_s",
    "nms_tex_WARRIORTILED_PAINT1": "nms_p",
    "nms_tex_WARRIORTILED_PAINTALT": "nms_s",
    "nms_tex_WARRIORSURFDETAIL_PAINT1": "nms_p",
    "nms_tex_WARRIORSURFDETAIL_PAINTALT": "nms_s",
    "nms_tex_WARRIORDISCOLOUR_PAINT1": "nms_p",
    "nms_tex_WARRIORDISCOLOUR_PAINTALT": "nms_s",
    "nms_tex_WARRIORMETALPAINTED2_PAINT": "nms_p",
}

PAINT_TAG = "charon_station_paint"
PAINT_VERSION = 1
PAINT_LABEL = "Charon station paint"
# tagged by the station library and seed_utils: tinted from the seed instead
STATION_DATA_TAG = "charon_station_data"
SEED_TINTED_TAG = "charon_station_tinted"
# sRGB -> linear, near enough for a tint
GAMMA = 2.2

_averages = {}


def ensure_station_paint(materials=None):
    """Tint the painted layers of every hull tile material in `materials` (all by default).
    Returns how many changed."""
    materials = materials if materials is not None else bpy.data.materials
    changed = 0
    for mat in materials:
        if mat is None or not mat.node_tree or mat.get(PAINT_TAG) == PAINT_VERSION:
            continue
        if mat.get(STATION_DATA_TAG) or mat.get(SEED_TINTED_TAG) or _has_colourise(mat):
            continue
        layers = _layer_images(mat.node_tree)
        if not layers:
            continue
        mat[PAINT_TAG] = PAINT_VERSION
        for tex, switch in layers.items():
            tint_texture(mat.node_tree, tex, PAINT_LAYERS[switch], linearise=True)
        changed += 1
    return changed


def is_painted(bpy_object):
    """True if any of its materials has tinted paint layers."""
    return any(slot.material is not None and slot.material.get(PAINT_TAG)
               for slot in bpy_object.material_slots)


def show_paint_layers(bpy_object):
    """Switch a decoration's painted layers on, so its colours show. Layers
    already on (or on another variant) are kept."""
    switches = [name for name in PAINT_LAYERS if bpy_object.get(name) == 0]
    if not switches or not is_painted(bpy_object):
        return
    for name in switches:
        bpy_object[name] = 1


def _has_colourise(mat):
    return any(node.type == "GROUP" and node.node_tree is not None
               and node.node_tree.name.startswith(COLOURISE_GROUP)
               for node in mat.node_tree.nodes)


def _layer_images(tree):
    """{image node: layer switch} for each painted layer, read off the links
    (Attribute -> compare -> Mix factor, image in the Mix's B)."""
    out = {}
    for attr in tree.nodes:
        if attr.type != "ATTRIBUTE":
            continue
        switch = attr.attribute_name.strip('[]"')
        if switch not in PAINT_LAYERS:
            continue
        gates = {link.to_node for socket in attr.outputs for link in socket.links}
        mixes = set()
        for gate in gates:
            if gate.type == "MATH":
                mixes |= {link.to_node for socket in gate.outputs for link in socket.links}
            elif gate.type == "MIX":
                mixes.add(gate)
        for mix in mixes:
            if mix.type != "MIX" or mix.data_type != "RGBA":
                continue
            for link in _socket(mix.inputs, "B_Color").links:
                if link.from_node.type == "TEX_IMAGE" and link.from_node.image:
                    out[link.from_node] = switch
    return out


def _socket(sockets, identifier):
    return next(s for s in sockets if s.identifier == identifier)


def average(image):
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


def tint_texture(tree, tex, attribute_name, linearise=False):
    """Tint one layer texture: texel + (colour - layer average) where the object has
    the property. Returns False when nothing reads the texture's colour."""
    nodes, links = tree.nodes, tree.links
    colour = tex.outputs["Color"]
    targets = [link.to_socket for link in colour.links]
    if not targets:
        return False
    x, y = tex.location
    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "OBJECT"
    attr.attribute_name = attribute_name
    attr.label = PAINT_LABEL if linearise else ""
    attr.location = (x + 300, y + 250)
    wanted = attr.outputs["Vector"]
    if linearise:
        gamma = nodes.new("ShaderNodeGamma")
        gamma.inputs["Gamma"].default_value = GAMMA
        gamma.location = (x + 400, y + 350)
        links.new(attr.outputs["Color"], gamma.inputs["Color"])
        wanted = gamma.outputs["Color"]
    shift = nodes.new("ShaderNodeVectorMath")
    shift.operation = "SUBTRACT"
    shift.inputs[1].default_value = average(tex.image)
    shift.location = (x + 500, y + 250)
    links.new(wanted, shift.inputs[0])
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
    return True
