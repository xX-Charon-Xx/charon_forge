"""Making the surfaces that glow in game glow in Blender.

The game decides this per material, from its MaterialClass and flags, which
the pipeline stamps onto every material as `nms_class` / `nms_flags`:

    _F07_UNLIT                 drawn with no lighting at all. The library
                               already wires these to emission (1770+ of them:
                               light strips, screens, holograms) - untouched.
    Glow, GlowTranslucent,     drawn again in the glow pass, but only where the
    Bloom                      masks texture's BLUE channel says so. Measured
                               on the library: blue is 0 on every ordinary
                               trim (BIGGSTRIM, BASEBUILDINGEXTERIOR,
                               ROVERTRIM) and covers ~1% of STONETRIM and
                               WOODTRIM - exactly their near-white light
                               strips (mean diffuse 0.91-0.97 there, against
                               0.44-0.54 overall). So emission = surface colour
                               x masks.B. A glow material with no masks map
                               (ExteriorLight_Mat, ResourceCube_mat) glows all
                               over in its own colour.
    Additive, GunAdditive,     light added on top of the scene: the whole
    DoublesidedAdditive        surface emits.

Before this pass, 555 glow-class materials - corvette exterior lamps, glow
plants, the light strips in stone and timber trim - rendered unlit.

Done per material, once: the material is tagged, and every placement shares
it.

How brightly - making lamps light the scene
-------------------------------------------
A part is one object with no children, so no Blender light objects are added:
the glowing surfaces ARE the lamp, and an emitting surface lights its
surroundings in Cycles (and EEVEE with raytracing). At strength 1 they look
right but throw almost nothing - a lamp's glowing area is a few square
centimetres. So every glow material's strength is multiplied by

    max(1, nms_glow)        an Attribute node, type OBJECT

which Blender looks up on the object and then on its mesh. The mesh of a part
whose game scenes hold LIGHT nodes gets

    nms_glow = (4 pi x sum of its lights' intensity) / (its emissive area)

- the watts the game's lights put out, spread over the surfaces that glow
(glow_boost below). Every other mesh has no nms_glow, reads 0, and stays at
strength 1. The unboosted value is kept as `nms_glow_lamp` so the Colours
panel can switch lamps off and on (set_lamps).

The Glow slider - every glow brighter at once
---------------------------------------------
On top of that, every glow strength is multiplied by

    1 + charon_glow_boost   an Attribute node, type VIEW_LAYER

which Blender looks up on the view layer, then the scene. The Watchtower's
Glow slider writes the scene's charon_glow_boost (set_glow), so one number
brightens every glowing surface in the file - no material is touched when it
moves. A scene without the property reads 0: glow as the game has it.
Materials wired before this (EMISSION_VERSION 2) get the multiplier added in
place (_add_scene_boost).
"""

import bpy

from .properties import MAT_CLASS, MAT_FLAGS

EMISSION_TAG = "charon_emission"
EMISSION_VERSION = 3
SCENE_GLOW_PROP = "charon_glow_boost"
SCENE_GLOW_LABEL = "Charon glow boost"

GLOW_PROP = "nms_glow"
GLOW_LAMP_PROP = "nms_glow_lamp"
GLOW_LABEL = "Charon glow"
# a lamp is never dimmer than its glow, and a stray huge game light (effect
# beams reach 90000) does not turn a strip into a sun
GLOW_MAX = 2000.0

MASKED_GLOW_CLASSES = {"Glow", "GlowTranslucent", "Bloom"}
ADDITIVE_CLASSES = {"Additive", "GunAdditive", "DoublesidedAdditive"}


def ensure_emission(materials=None):
    """Wire emission into every library material the game draws glowing.

    Returns:
        int: How many materials were changed.
    """
    materials = materials if materials is not None else bpy.data.materials
    changed = 0
    for mat in materials:
        if mat is None or not mat.node_tree or MAT_CLASS not in mat:
            continue
        tag = mat.get(EMISSION_TAG)
        if tag == EMISSION_VERSION:
            continue
        mat[EMISSION_TAG] = EMISSION_VERSION
        if tag == 2:
            if _add_scene_boost(mat.node_tree):
                changed += 1
        elif _wire(mat):
            changed += 1
    return changed


def glow_kind(mat):
    """'unlit', 'masked', 'whole' or None - how the game lights a material."""
    flags = set(mat.get(MAT_FLAGS) or [])
    cls = mat.get(MAT_CLASS, "")
    if "_F07_UNLIT" in flags:
        return "unlit"
    if cls in MASKED_GLOW_CLASSES:
        return "masked" if _masks_blue(mat.node_tree, create=False) is not None \
            or _masks_image(mat.node_tree) is not None else "whole"
    if cls in ADDITIVE_CLASSES:
        return "whole"
    return None


def _wire(mat):
    kind = glow_kind(mat)
    if kind is None:
        return False
    tree = mat.node_tree
    bsdf = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return False

    base = bsdf.inputs["Base Color"]
    colour = bsdf.inputs["Emission Color"]
    strength = bsdf.inputs["Emission Strength"]
    # an unlit surface already emits its diffuse (and has a black base);
    # only its strength gets the lamp scale
    if kind != "unlit":
        if base.is_linked:
            tree.links.new(base.links[0].from_socket, colour)
        else:
            colour.default_value = base.default_value

    if kind == "unlit":
        source = strength.links[0].from_socket if strength.is_linked else None
    elif kind == "masked":
        source = _masks_blue(tree, create=True)
        if source is None:
            return False
    else:
        source = None
        strength.default_value = 1.0
    _scale_by_glow(tree, strength, source)
    return True


def _scale_by_glow(tree, strength, source):
    """strength = (source or its value) x max(1, object/mesh nms_glow)."""
    x, y = strength.node.location.x, strength.node.location.y
    attr = tree.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "OBJECT"
    attr.attribute_name = GLOW_PROP
    attr.label = GLOW_LABEL
    attr.location = (x - 700, y - 650)
    floor = tree.nodes.new("ShaderNodeMath")
    floor.operation = "MAXIMUM"
    floor.inputs[1].default_value = 1.0
    floor.label = GLOW_LABEL
    floor.location = (x - 480, y - 650)
    tree.links.new(attr.outputs["Fac"], floor.inputs[0])
    times = tree.nodes.new("ShaderNodeMath")
    times.operation = "MULTIPLY"
    times.label = GLOW_LABEL
    times.location = (x - 260, y - 650)
    if source is not None:
        tree.links.new(source, times.inputs[0])
    else:
        times.inputs[0].default_value = strength.default_value
    tree.links.new(floor.outputs["Value"], times.inputs[1])
    tree.links.new(times.outputs["Value"], strength)
    _add_scene_boost(tree)


def _add_scene_boost(tree):
    """Put x (1 + scene charon_glow_boost) between the glow strength and the
    Principled BSDF. Only where the strength comes from the Charon glow chain,
    and only once."""
    bsdf = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return False
    strength = bsdf.inputs["Emission Strength"]
    if not strength.is_linked:
        return False
    source_node = strength.links[0].from_node
    if source_node.label != GLOW_LABEL:
        return False
    x, y = source_node.location.x, source_node.location.y
    attr = tree.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "VIEW_LAYER"
    attr.attribute_name = SCENE_GLOW_PROP
    attr.label = SCENE_GLOW_LABEL
    attr.location = (x - 220, y - 220)
    one_plus = tree.nodes.new("ShaderNodeMath")
    one_plus.operation = "ADD"
    one_plus.inputs[1].default_value = 1.0
    one_plus.label = SCENE_GLOW_LABEL
    one_plus.location = (x, y - 220)
    tree.links.new(attr.outputs["Fac"], one_plus.inputs[0])
    boost = tree.nodes.new("ShaderNodeMath")
    boost.operation = "MULTIPLY"
    boost.label = SCENE_GLOW_LABEL
    boost.location = (x + 220, y - 110)
    tree.links.new(source_node.outputs[0], boost.inputs[0])
    tree.links.new(one_plus.outputs[0], boost.inputs[1])
    tree.links.new(boost.outputs[0], strength)
    return True


def set_glow(scene, multiplier):
    """Every glow in the scene x multiplier (1 = the game's own)."""
    value = max(0.0, float(multiplier)) - 1.0
    if abs(scene.get(SCENE_GLOW_PROP, 0.0) - value) < 1e-6:
        return
    scene[SCENE_GLOW_PROP] = value
    # a view layer attribute is read when the scene is evaluated
    scene.update_tag()
    for layer in scene.view_layers:
        layer.update()


# Lamps ---
def glow_boost(mesh, object_id):
    """nms_glow for a part's mesh: its game lights' watts over its emissive
    area, or None when it has no lights or nothing glows."""
    import numpy as np
    from . import game_data

    watts = game_data.light_power(object_id)
    if watts <= 0.0 or not mesh.polygons:
        return None
    glowing = [i for i, mat in enumerate(mesh.materials)
               if mat is not None and MAT_CLASS in mat and glow_kind(mat)]
    if not glowing:
        return None
    area = np.empty(len(mesh.polygons), np.float32)
    mesh.polygons.foreach_get("area", area)
    index = np.empty(len(mesh.polygons), np.int32)
    mesh.polygons.foreach_get("material_index", index)
    lit = float(area[np.isin(index, glowing)].sum())
    if lit <= 1e-6:
        return None
    return float(min(GLOW_MAX, max(1.0, watts / lit)))


def stamp_glow(mesh, object_id):
    """Store a lamp mesh's boost; applied now unless lamps are switched off."""
    boost = glow_boost(mesh, object_id)
    if boost is None:
        return None
    mesh[GLOW_LAMP_PROP] = boost
    mesh[GLOW_PROP] = boost if lamps_on() else 1.0
    return boost


def lamps_on(scene=None):
    scene = scene or getattr(bpy.context, "scene", None)
    if scene is None:
        return True
    # the Watchtower's game lamp layer lights the scene instead (see
    # lighting/game_lights.py) - a lamp is never counted twice
    lighting = getattr(scene, "charon_lighting", None)
    if lighting is not None and lighting.enabled and lighting.game_lights:
        return False
    return bool(getattr(scene, "charon_lamps", True))


def set_lamps(enabled):
    """Lamps lighting the scene (their game power) or just glowing (1)."""
    for mesh in bpy.data.meshes:
        if GLOW_LAMP_PROP in mesh:
            mesh[GLOW_PROP] = mesh[GLOW_LAMP_PROP] if enabled else 1.0
            mesh.update_tag()


def _masks_image(tree):
    for node in tree.nodes:
        if node.type == "TEX_IMAGE" and node.image is not None \
                and ".MASKS" in node.image.name.upper():
            return node
    return None


def _feeds_from_masks(socket, depth=0):
    """True when an upstream image of `socket` is a MASKS texture. The finish
    rig puts a chain of Mix nodes between the slices and the Separate node,
    so this walks back through them."""
    if depth > 12 or not socket.is_linked:
        return False
    node = socket.links[0].from_node
    if node.type == "TEX_IMAGE":
        return node.image is not None and ".MASKS" in node.image.name.upper()
    return any(_feeds_from_masks(s, depth + 1) for s in node.inputs if s.is_linked)


def _masks_blue(tree, create):
    """The Blue output of the node that splits the (finish-switched) masks
    texture - the same colour the roughness and metal come from."""
    for node in tree.nodes:
        if node.type == "SEPARATE_COLOR" and _feeds_from_masks(node.inputs[0]):
            return node.outputs["Blue"]
    if not create:
        return None
    image = _masks_image(tree)
    if image is None:
        return None
    split = tree.nodes.new("ShaderNodeSeparateColor")
    split.label = "Glow mask (masks B)"
    split.location = (image.location.x + 250, image.location.y - 200)
    tree.links.new(image.outputs["Color"], split.inputs[0])
    return split.outputs["Blue"]
