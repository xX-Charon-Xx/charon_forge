"""Colouring the colourable materials that have no colourise mask.

The pipeline gives a material the NMS_Colourise group only when the game
material has a colourise mask texture to feed it. Some are flagged
_F53_COLOURISABLE with no mask at all (BASE_CAVE2's CaveLeaves_Mat, the lava
of BASE_CAVE5, ...) and came out of the pipeline with no colour nodes, so
recolouring those parts did nothing.

With no mask there is nothing to pick the secondary, ternary or quaternary
regions, so the whole surface takes the primary colour: the diffuse is
multiplied by the object's nms_p, the same property the colourise group
reads. Done per material, once - the material is tagged, and every placement
shares it.
"""

import bpy

from .properties import COLOURISE_GROUP, MAT_FLAGS, SLOT_PROPS

COLOURISE_FLAG = "_F53_COLOURISABLE"
UNLIT_FLAG = "_F07_UNLIT"

TINT_TAG = "charon_primary_tint"
TINT_VERSION = 1
TINT_LABEL = "Charon primary tint"


def ensure_colourise(materials=None):
    """Tint every colourable library material that has no colourise group.

    Returns:
        int: How many materials were changed.
    """
    materials = materials if materials is not None else bpy.data.materials
    changed = 0
    for mat in materials:
        if mat is None or not mat.node_tree or MAT_FLAGS not in mat:
            continue
        if mat.get(TINT_TAG) == TINT_VERSION:
            continue
        mat[TINT_TAG] = TINT_VERSION
        if needs_tint(mat) and _wire(mat):
            changed += 1
    return changed


def needs_tint(mat):
    """Colourable in game, with nothing in its node tree reading the palette."""
    if COLOURISE_FLAG not in set(mat.get(MAT_FLAGS) or []):
        return False
    for node in mat.node_tree.nodes:
        if node.type == "GROUP" and node.node_tree is not None \
                and node.node_tree.name.startswith(COLOURISE_GROUP):
            return False
    return True


def _socket(sockets, name, kind):
    return next(s for s in sockets if s.name == name and s.type == kind)


def _wire(mat):
    tree = mat.node_tree
    bsdf = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return False

    # an unlit surface shows its diffuse through emission, over a black base
    unlit = UNLIT_FLAG in set(mat.get(MAT_FLAGS) or [])
    target = bsdf.inputs["Emission Color" if unlit else "Base Color"]
    source = target.links[0].from_socket if target.is_linked else None

    x, y = bsdf.location.x, bsdf.location.y
    attr = tree.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "OBJECT"
    attr.attribute_name = SLOT_PROPS[0]
    attr.label = TINT_LABEL
    attr.location = (x - 520, y + 260)

    mix = tree.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.label = TINT_LABEL
    mix.location = (x - 260, y + 260)
    mix.inputs[0].default_value = 1.0
    a = _socket(mix.inputs, "A", "RGBA")
    if source is not None:
        tree.links.new(source, a)
    else:
        a.default_value = target.default_value
    tree.links.new(attr.outputs["Color"], _socket(mix.inputs, "B", "RGBA"))
    result = _socket(mix.outputs, "Result", "RGBA")
    tree.links.new(result, target)

    # emission.py copies the base colour into Emission Color for glowing
    # materials; one already wired from the untinted source follows it
    if not unlit and source is not None:
        emission = bsdf.inputs["Emission Color"]
        if emission.is_linked and emission.links[0].from_socket == source:
            tree.links.new(result, emission)
    return True
