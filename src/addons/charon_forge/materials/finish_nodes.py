"""The shader nodes that let a finish change a high res part's surface.

A part's roughness, metal and diffuse maps are shared by every placement of
it, so a finish cannot be baked into them any more than the colour can.
Instead each colourable material gets a few nodes spliced in front of its
Principled BSDF that read the finish off object properties - the same trick
the colour slots use. See properties.PROP_FINISH_*.
"""

import bpy

from .deferral import should_defer
from .properties import (COLOURISE_GROUP, FINISH_NODE_LABEL, FINISH_NODES_TAG,
                         FINISH_NODES_VERSION, PROP_FINISH_METALLIC,
                         PROP_FINISH_POLISH, PROP_FINISH_ROUGHNESS,
                         PROP_FINISH_TINT, PROP_FINISH_TINT_MIX)


def ensure_finish_nodes(materials=None):
    """Give materials the nodes that let a finish change their surface.

    Idempotent and cheap to call again: a material that already carries the
    nodes is skipped by its marker, so re-importing an asset does not stack a
    second copy of them.

    Args:
        materials (iterable): Materials to fix up. Defaults to all of them.

    Returns:
        int: How many materials were changed.
    """
    if materials is None and should_defer():
        return 0

    materials = materials if materials is not None else bpy.data.materials

    changed = 0
    for mat in materials:
        if mat is None or not mat.node_tree:
            continue

        version = mat.get(FINISH_NODES_TAG)
        if version == FINISH_NODES_VERSION:
            continue

        # Only the materials that carry the colourise group. That keeps this off
        # the flat proxy materials and off anything of the user's own, and it
        # also leaves a part's non-paintable materials - its lights and its glass
        # - alone, which is right: a weathered finish should dull the hull, not
        # the lamps set into it.
        if not any(node.type == 'GROUP' and node.node_tree
                   and node.node_tree.name.startswith(COLOURISE_GROUP)
                   for node in mat.node_tree.nodes):
            continue

        principled = next((node for node in mat.node_tree.nodes
                           if node.type == 'BSDF_PRINCIPLED'), None)
        if principled is None:
            # not a shaded material - nothing a finish could act on
            continue

        # A material carrying an older network - almost always one that came
        # back with a saved scene - is stripped before being rebuilt, so the
        # new shape replaces it instead of stacking on top of it.
        if version:
            _clear_finish_nodes(mat.node_tree, principled)

        _splice_finish_roughness(mat.node_tree, principled.inputs["Roughness"])
        _splice_finish_offset(mat.node_tree, principled.inputs["Metallic"],
                              PROP_FINISH_METALLIC,
                              FINISH_NODE_LABEL + " Metallic")
        _splice_finish_tint(mat.node_tree, principled.inputs["Base Color"])

        mat[FINISH_NODES_TAG] = FINISH_NODES_VERSION
        changed += 1

    return changed


def _splice_finish_roughness(node_tree, socket):
    """Let a finish both polish and roughen whatever already feeds Roughness.

    Roughness gets a proportional term as well as an offset - see
    properties.PROP_FINISH_POLISH for why an offset alone could not produce a
    gloss:

        roughness = texture * (1 - polish) + offset

    clamped back into 0..1. With both properties absent, which is what an
    Attribute node reports for an object that has never been given a finish,
    this is texture * 1 + 0 - exactly the value the maps carry.
    """
    nodes = node_tree.nodes
    links = node_tree.links
    origin = socket.node.location

    polish = nodes.new("ShaderNodeAttribute")
    polish.attribute_type = 'OBJECT'
    polish.attribute_name = PROP_FINISH_POLISH
    polish.label = FINISH_NODE_LABEL + " Polish"
    polish.location = (origin.x - 900, origin.y - 400)

    # (1 - polish), so the stored 0 means "keep all of it"
    keep = nodes.new("ShaderNodeMath")
    keep.operation = 'SUBTRACT'
    keep.label = FINISH_NODE_LABEL + " Polish"
    keep.location = (origin.x - 620, origin.y - 400)
    keep.inputs[0].default_value = 1.0
    links.new(polish.outputs["Fac"], keep.inputs[1])

    offset = nodes.new("ShaderNodeAttribute")
    offset.attribute_type = 'OBJECT'
    offset.attribute_name = PROP_FINISH_ROUGHNESS
    offset.label = FINISH_NODE_LABEL + " Roughness"
    offset.location = (origin.x - 620, origin.y - 620)

    # texture * keep + offset. inputs are (Value, Multiplier, Addend), all
    # named "Value", so they go by index.
    combine = nodes.new("ShaderNodeMath")
    combine.operation = 'MULTIPLY_ADD'
    combine.use_clamp = True
    combine.label = FINISH_NODE_LABEL + " Roughness"
    combine.location = (origin.x - 300, origin.y - 400)

    existing = socket.links[0].from_socket if socket.is_linked else None
    if existing is not None:
        links.new(existing, combine.inputs[0])
    else:
        combine.inputs[0].default_value = socket.default_value

    links.new(keep.outputs["Value"], combine.inputs[1])
    links.new(offset.outputs["Fac"], combine.inputs[2])
    links.new(combine.outputs["Value"], socket)


def _splice_finish_offset(node_tree, socket, attribute_name, label):
    """Add an object attribute onto whatever already feeds `socket`, clamped
    back into 0..1.

    Args:
        node_tree (bpy.types.NodeTree): The material's node tree.
        socket (bpy.types.NodeSocket): The Principled input to drive.
        attribute_name (str): The object property carrying the offset.
        label (str): Label for the added nodes, so they are findable by hand.
    """
    nodes = node_tree.nodes
    links = node_tree.links

    attribute = nodes.new("ShaderNodeAttribute")
    attribute.attribute_type = 'OBJECT'
    attribute.attribute_name = attribute_name
    attribute.label = label
    attribute.location = (socket.node.location.x - 600,
                          socket.node.location.y - 400)

    add = nodes.new("ShaderNodeMath")
    add.operation = 'ADD'
    add.use_clamp = True
    add.label = label
    add.location = (socket.node.location.x - 300,
                    socket.node.location.y - 400)

    # whatever was feeding the socket becomes the first term - a texture, or the
    # value that was typed into it if nothing was linked
    existing = socket.links[0].from_socket if socket.is_linked else None
    if existing is not None:
        links.new(existing, add.inputs[0])
    else:
        add.inputs[0].default_value = socket.default_value

    links.new(attribute.outputs["Fac"], add.inputs[1])
    links.new(add.outputs["Value"], socket)


def _splice_finish_tint(node_tree, socket):
    """Wash a finish colour over whatever already feeds Base Color.

    Rust is a colour as much as a roughness, and the part's own diffuse map
    cannot carry it - that map is shared by every placement. So the tint goes
    on as a mix at the end of the chain, driven by two object properties, the
    same way the palette and the roughness are.
    """
    nodes = node_tree.nodes
    links = node_tree.links

    colour = nodes.new("ShaderNodeAttribute")
    colour.attribute_type = 'OBJECT'
    colour.attribute_name = PROP_FINISH_TINT
    colour.label = FINISH_NODE_LABEL + " Tint"
    colour.location = (socket.node.location.x - 900, socket.node.location.y + 300)

    amount = nodes.new("ShaderNodeAttribute")
    amount.attribute_type = 'OBJECT'
    amount.attribute_name = PROP_FINISH_TINT_MIX
    amount.label = FINISH_NODE_LABEL + " Tint Mix"
    amount.location = (socket.node.location.x - 900, socket.node.location.y + 120)

    mix = nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    # MULTIPLY, not MIX. Mixing towards a flat colour washes the panel lines,
    # decals and paint straight off the part - 60% towards a rust brown turned
    # a hull into a smooth terracotta shape. Multiplying darkens and shifts the
    # hue while every bit of that detail survives underneath.
    mix.blend_type = 'MULTIPLY'
    mix.clamp_factor = True
    mix.label = FINISH_NODE_LABEL + " Tint"
    mix.location = (socket.node.location.x - 300, socket.node.location.y + 220)

    existing = socket.links[0].from_socket if socket.is_linked else None
    if existing is not None:
        links.new(existing, mix.inputs["A"])
    else:
        mix.inputs["A"].default_value = socket.default_value

    links.new(amount.outputs["Fac"], mix.inputs["Factor"])
    links.new(colour.outputs["Color"], mix.inputs["B"])
    links.new(mix.outputs["Result"], socket)


def _is_finish_node(node):
    """True for a node the splice added."""
    return (node.label or "").startswith(FINISH_NODE_LABEL)


def _unsplice(socket):
    """Put back whatever fed `socket` before the finish nodes went in.

    Every node the splice puts in front of a Principled input takes the
    original on its first usable input - inputs[0] on a Math node, "A" on the
    Mix - so undoing one is a matter of reading that back out. The nodes
    themselves are left for the caller to remove once every socket is done.
    """
    if not socket.is_linked:
        return

    spliced = socket.links[0].from_node
    if not _is_finish_node(spliced):
        return

    carried = spliced.inputs["A" if spliced.bl_idname == "ShaderNodeMix" else 0]
    node_tree = socket.node.id_data
    node_tree.links.remove(socket.links[0])

    if carried.is_linked:
        node_tree.links.new(carried.links[0].from_socket, socket)
    else:
        socket.default_value = carried.default_value


def _clear_finish_nodes(node_tree, principled):
    """Strip a previous version's finish network out of a material."""
    for name in ("Roughness", "Metallic", "Base Color"):
        _unsplice(principled.inputs[name])

    for node in [n for n in node_tree.nodes if _is_finish_node(n)]:
        node_tree.nodes.remove(node)
