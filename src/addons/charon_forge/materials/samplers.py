"""Keeping materials under EEVEE's texture sampler limit.

A GPU shader can bind at most 32 textures, and EEVEE takes some of those for
itself. Every Image Texture node in a material is compiled in, whichever one
a switch actually shows, so a material that carries many alternatives fails
to compile ("profile doesn't support more than 32 samplers") and draws as
nothing.

The pipeline builds such materials for the game's procedural texture
variants: U_SILO_S's number decal carries all 26 alternative numbers
(NUMBER.BASE.A1 ... C9) behind a switch read from the object property
nms_tex_NUMBER_BASE, listed on the material as

    nms_texture_variants = {"nms_tex_NUMBER_BASE": ["(as named)", "C9", ...]}

The first label in each list is the family's default - "(as named)", "OFF"
or a texture's own name. When a material is over budget, its variant images
are all pointed at one image: the family image the list does not name when
there is exactly one (the default's own), else the image of the first listed
variant (a default of "OFF" shows no variant image at all, so its look is
unchanged). Blender binds an image once however many nodes sample it, so
the material drops under the limit and compiles; the cost is that the
variants all show that one image. The switch nodes are left as they are, and which image
each node had is kept on the material (charon_variant_images), so this can
be undone.

Done per material, once - the material is tagged.
"""

import json
import os

import bpy

VARIANTS_PROP = "nms_texture_variants"
VARIANT_PREFIX = "nms_tex_"

SAMPLER_TAG = "charon_samplers"
SAMPLER_VERSION = 1
# node name -> image name, for every node repointed
ORIGINAL_IMAGES_PROP = "charon_variant_images"

# Distinct images a material may sample before its variants are collapsed.
# 32 is the hardware limit; EEVEE's own lighting, shadow and utility
# textures take most of the rest. Set no lower than it has to be: a material
# collapsed here loses its variants.
MAX_MATERIAL_IMAGES = 24


def _image_nodes(node_tree, seen=None):
    """Every Image Texture node in a tree, node groups included."""
    seen = set() if seen is None else seen
    if node_tree is None or node_tree in seen:
        return []
    seen.add(node_tree)
    nodes = []
    for node in node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image is not None:
            nodes.append(node)
        elif node.type == "GROUP":
            nodes.extend(_image_nodes(node.node_tree, seen))
    return nodes


def _stem(image):
    """An image's texture name without folder or extension, upper case."""
    path = image.filepath or image.name
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return os.path.splitext(name)[0].upper()


def _variant_families(mat):
    """[(family stem, [variant labels in order])] from nms_texture_variants.

    "nms_tex_NUMBER_BASE" names the texture family NUMBER.BASE; its labels
    are the suffixes of the family's variant images (NUMBER.BASE.C9, ...).
    """
    raw = mat.get(VARIANTS_PROP)
    if not raw:
        return []
    try:
        variants = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, ValueError):
        return []

    families = []
    for key, labels in variants.items():
        if not key.startswith(VARIANT_PREFIX) or not isinstance(labels, (list, tuple)):
            continue
        family = key[len(VARIANT_PREFIX):].upper()
        families.append((family, [str(label).upper() for label in labels]))
    return families


def _family_key(stem):
    # the property key has "_" where the texture name has "."
    return stem.replace(".", "_")


def _collapse_variants(mat, nodes):
    """Point each variant family's images at its default. Returns nodes changed."""
    changed = {}
    for family, labels in _variant_families(mat):
        members = []
        for node in nodes:
            stem = _stem(node.image)
            head, _, label = stem.rpartition(".")
            if head and _family_key(head) == family:
                members.append((node, label))
        if not members:
            continue

        # the family image the list does not name, when there is exactly one
        # - the default's own - else the first listed variant's
        unnamed = {node.image for node, label in members if label not in labels}
        if len(unnamed) == 1:
            default = next(iter(unnamed))
        else:
            by_label = {label: node.image for node, label in members}
            default = next((by_label[label] for label in labels if label in by_label), None)
        if default is None:
            continue

        for node, label in members:
            if node.image != default:
                changed[node.name] = node.image.name
                node.image = default
    return changed


def ensure_sampler_budget(materials=None):
    """Collapse the texture variants of every material over the budget.

    Returns:
        int: How many materials were changed.
    """
    materials = materials if materials is not None else bpy.data.materials
    changed_count = 0
    for mat in materials:
        if mat is None or not mat.node_tree:
            continue
        if mat.get(SAMPLER_TAG) == SAMPLER_VERSION:
            continue
        mat[SAMPLER_TAG] = SAMPLER_VERSION

        nodes = _image_nodes(mat.node_tree)
        if len({node.image for node in nodes}) <= MAX_MATERIAL_IMAGES:
            continue

        changed = _collapse_variants(mat, nodes)
        if changed:
            mat[ORIGINAL_IMAGES_PROP] = json.dumps(changed)
            changed_count += 1

        remaining = len({node.image for node in _image_nodes(mat.node_tree)})
        if remaining > MAX_MATERIAL_IMAGES:
            print(
                "Charon Forge: %s still samples %d textures, EEVEE may not "
                "be able to draw it" % (mat.name, remaining)
            )
    return changed_count
