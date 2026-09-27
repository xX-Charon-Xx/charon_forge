"""One material per distinct material, across every library part appended.

Each library .blend carries its own copies of the materials it shares with
other parts, so a ship's worth of parts appends hundreds of materials that
are the same thing. Their number is what makes appending slow: Blender
revisits every material's node tree on each append, so each asset costs more
than the last. Measured on a 2339 part corvette (74 assets, Blender 5.1):

    kept as appended     530 materials   appending 5.4 s
    merged as appended   181 materials   appending 1.9 s + 0.8 s merging

and every import after that into the same file is cheaper too.

A material only merges into another when nothing a render can see tells them
apart - every editable property of the material and of each node (by name),
every unlinked socket value, every link, every custom property but the
pipeline's own bookkeeping, and the images (by file) and node groups (by
name, which dedupe.py collapses anyway) they point at.

That comparison is made on the material as it was appended, before
prepare_materials changes it, and stored on it as PROP_KEY. A later asset's
copy is matched against the stored key, so it merges into one already
prepared: preparing is decided by the material's own content, so the two
would come out the same.
"""

import hashlib
import os
import re

import bpy

# the comparison's digest, on every material this has seen
PROP_KEY = "charon_material_key"

# pipeline bookkeeping nothing reads, which differs between identical copies
IGNORED_PROPS = {"nms_material_path", "nms_procedural_definition",
                 "nms_diffuse_gain", PROP_KEY}

# a node's UI state, not its shading
_UI_PROPS = {"name", "label", "location", "width", "height", "select", "hide",
             "show_options", "show_preview", "show_texture", "color",
             "use_custom_color", "parent", "location_absolute",
             "warning_propagation"}

# what every datablock has about itself - `original` points at the block
# itself, so leaving it in makes every material unique
_ID_PROPS = {"original", "library", "library_weak_reference", "override_library",
             "asset_data", "preview", "node_tree"}

_COPY_SUFFIX = re.compile(r"\.\d{3}$")


class _Unknown(Exception):
    """A setting this cannot compare - the material is left unmerged."""


def _value(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (bool, int, str)) or value is None:
        return value
    try:
        return tuple(_value(v) for v in value)
    except TypeError:
        raise _Unknown(type(value).__name__)


def _ident(block):
    if isinstance(block, bpy.types.Image):
        return ("IMAGE", os.path.normcase(bpy.path.abspath(block.filepath)),
                block.colorspace_settings.name, block.alpha_mode)
    return (type(block).__name__, _COPY_SUFFIX.sub("", block.name))


def _props(struct, skip):
    out = []
    for prop in struct.bl_rna.properties:
        key = prop.identifier
        if key in skip or key == "rna_type":
            continue
        if prop.type == "POINTER":
            target = getattr(struct, key)
            if target is None:
                out.append((key, None))
            elif isinstance(target, bpy.types.ID):
                out.append((key, _ident(target)))
            elif isinstance(target, bpy.types.ColorRamp):
                out.append((key, (target.color_mode, target.interpolation,
                                  target.hue_interpolation,
                                  tuple((_value(e.position), _value(e.color))
                                        for e in target.elements))))
            elif isinstance(target, bpy.types.CurveMapping):
                out.append((key, tuple(
                    tuple((_value(p.location), p.handle_type) for p in curve.points)
                    for curve in target.curves)))
            elif isinstance(target, bpy.types.PropertyGroup):
                out.append((key, _props(target, ())))
            elif key == "image_user":
                out.append((key, (target.frame_offset, target.frame_start,
                                  target.frame_duration, target.use_cyclic)))
            elif not prop.is_readonly:
                raise _Unknown("%s.%s" % (struct.bl_rna.identifier, key))
            continue
        if prop.is_readonly or prop.type == "COLLECTION":
            continue
        out.append((key, _value(getattr(struct, key))))
    return tuple(out)


def _custom(block):
    out = []
    for key in sorted(block.keys()):
        if key in IGNORED_PROPS:
            continue
        value = block[key]
        if hasattr(value, "to_dict"):
            value = value.to_dict()
        elif hasattr(value, "to_list"):
            value = value.to_list()
        out.append((key, repr(value)))
    return tuple(out)


def material_key(mat):
    """The digest two materials share exactly when they render the same, or
    None when the material has a setting this cannot compare."""
    try:
        parts = [_props(mat, _UI_PROPS | _ID_PROPS), _custom(mat)]
        tree = mat.node_tree
        if tree is not None:
            for node in sorted(tree.nodes, key=lambda n: n.name):
                parts.append((node.bl_idname, node.name, _props(node, _UI_PROPS),
                              tuple((s.identifier, _value(s.default_value))
                                    for s in node.inputs
                                    if not s.is_linked and hasattr(s, "default_value"))))
            parts.append(tuple(sorted(
                (l.from_node.name, l.from_socket.identifier, l.to_node.name,
                 l.to_socket.identifier, l.is_muted) for l in tree.links)))
    except _Unknown:
        return None
    return hashlib.sha1(repr(parts).encode("utf-8")).hexdigest()


# {key: material} for the file's keyed materials, kept between appends; it
# is rebuilt whenever the file's material count isn't what the last call left
# it at, which catches a new file, an undo or anything else adding or
# removing materials
_known = {}
_known_count = -1


def _known_materials(fresh):
    global _known, _known_count
    if len(bpy.data.materials) != _known_count + len(fresh):
        _known = {}
        for mat in bpy.data.materials:
            key = mat.get(PROP_KEY)
            if key is not None and mat not in fresh and mat.library is None:
                _known.setdefault(key, mat)
    return _known


def _alive(mat, key):
    try:
        return mat.get(PROP_KEY) == key
    except ReferenceError:
        return False


def merge_appended(mesh):
    """Point a freshly appended mesh's materials at the ones already in the
    file that are the same, and remove its copies.

    Only materials without a key are looked at - an append always brings
    fresh copies, so those are exactly the new ones, and nothing but this
    mesh uses them yet: its slots are repointed directly rather than through
    user_remap, which would search the whole file for each.

    Returns:
        int: Materials merged away.
    """
    global _known_count
    fresh = {mat for mat in mesh.materials
             if mat is not None and mat.library is None and PROP_KEY not in mat}
    if not fresh:
        return 0

    known = _known_materials(fresh)
    swap = {}
    for mat in sorted(fresh, key=lambda m: m.name):
        key = material_key(mat)
        if key is None:
            continue
        canonical = known.get(key)
        if canonical is not None and not _alive(canonical, key):
            canonical = None
        if canonical is None:
            mat[PROP_KEY] = key
            known[key] = mat
        else:
            swap[mat] = canonical

    if swap:
        for index, mat in enumerate(mesh.materials):
            if mat in swap:
                mesh.materials[index] = swap[mat]
        bpy.data.batch_remove([mat for mat in swap if mat.users == 0])
    _known_count = len(bpy.data.materials)
    return len(swap)
