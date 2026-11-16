"""Removes the old hand-tuned finish preview nodes from scenes saved before
the game's finish textures; materials without the marker are untouched."""

import bpy

from .properties import (LEGACY_FINISH_NODE_LABEL, LEGACY_FINISH_NODES_TAG,
                         LEGACY_FINISH_PROPS)


def strip_legacy_finish_nodes(materials=None):
    """Remove the old finish splice from materials that carry it; returns how many."""
    materials = materials if materials is not None else bpy.data.materials
    cleaned = 0
    for mat in materials:
        if mat is None or LEGACY_FINISH_NODES_TAG not in mat or not mat.node_tree:
            continue
        principled = next((n for n in mat.node_tree.nodes
                           if n.type == 'BSDF_PRINCIPLED'), None)
        if principled is not None:
            for name in ("Roughness", "Metallic", "Base Color"):
                _unsplice(principled.inputs[name])
        for node in [n for n in mat.node_tree.nodes if _is_legacy_node(n)]:
            mat.node_tree.nodes.remove(node)
        del mat[LEGACY_FINISH_NODES_TAG]
        cleaned += 1
    return cleaned


def strip_legacy_finish_props(objects=None):
    """Drop the old finish offsets from objects. Returns how many had any."""
    objects = objects if objects is not None else bpy.data.objects
    touched = 0
    for obj in objects:
        found = [p for p in LEGACY_FINISH_PROPS if p in obj]
        for prop in found:
            del obj[prop]
        touched += bool(found)
    return touched


def _is_legacy_node(node):
    return (node.label or "").startswith(LEGACY_FINISH_NODE_LABEL)


def _unsplice(socket):
    """Put back whatever fed `socket` before the old nodes went in
    (kept on each spliced node's first input)."""
    if not socket.is_linked:
        return
    spliced = socket.links[0].from_node
    if not _is_legacy_node(spliced):
        return
    carried = spliced.inputs["A" if spliced.bl_idname == "ShaderNodeMix" else 0]
    node_tree = socket.node.id_data
    node_tree.links.remove(socket.links[0])
    if carried.is_linked:
        node_tree.links.new(carried.links[0].from_socket, socket)
    else:
        socket.default_value = carried.default_value
