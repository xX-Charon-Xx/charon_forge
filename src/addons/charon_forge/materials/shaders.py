"""How many shaders EEVEE will compile for a set of materials.

EEVEE does not compile a shader per material. It generates GLSL from the
part of the node tree that reaches the output and caches the compiled pass
by a hash of that code (GPUPassCache, source/blender/gpu/intern/gpu_pass.cc),
so every material that generates the same code shares one compile. Unlinked
socket values and the images a node samples go in as uniforms and textures,
not code - two materials that differ only in those are one shader.

So what an import costs to compile is the number of distinct node
STRUCTURES among its materials, and how big each is - not the number of
materials. shader_signature() approximates the code hash from Python: the
nodes that reach the output, their settings, which sockets are linked and
how, and the material settings that pick a pipeline. It over-counts rather
than under-counts: a setting it can't tell is compiled in counts as if it is.

A material that is not plainly opaque (its Alpha linked or below 1, or drawn
blended) needs shadow and depth passes of its own; an opaque one uses
EEVEE's shared default ones. Those are counted too.
"""

import hashlib

import bpy

# a node's UI state and the values EEVEE passes in as uniforms, not code
_SKIP_PROPS = {"rna_type", "name", "label", "location", "location_absolute",
               "width", "height", "select", "hide", "show_options",
               "show_preview", "show_texture", "color", "use_custom_color",
               "parent", "warning_propagation", "image", "image_user",
               "is_active_output", "bl_idname", "bl_label", "bl_description",
               "bl_icon", "bl_static_type", "bl_width_default",
               "bl_width_min", "bl_width_max", "bl_height_default",
               "bl_height_min", "bl_height_max", "type", "internal_links",
               "dimensions", "inputs", "outputs", "mute"}

# the material settings that choose how EEVEE draws it
_MATERIAL_PROPS = ("surface_render_method", "blend_method", "use_backface_culling",
                   "use_backface_culling_shadow", "use_transparent_shadow",
                   "use_transparency_overlap", "displacement_method",
                   "use_raytrace_refraction", "use_screen_refraction",
                   "thickness_mode", "volume_intersection_method")


def _output_node(tree, kind):
    outputs = [node for node in tree.nodes if node.bl_idname == kind]
    for node in outputs:
        if getattr(node, "is_active_output", False):
            return node
    return outputs[0] if outputs else None


def _node_settings(node):
    """The node's own settings that can change the code it generates."""
    out = []
    for prop in node.bl_rna.properties:
        key = prop.identifier
        if key in _SKIP_PROPS or prop.type in {"POINTER", "COLLECTION", "FLOAT"}:
            continue
        try:
            value = getattr(node, key)
        except (AttributeError, TypeError):
            continue
        if prop.type == "ENUM" and prop.is_enum_flag:
            value = tuple(sorted(value))
        out.append((key, value))
    return tuple(out)


def _tree_signature(tree, output_kind, groups):
    """The reachable part of a tree, in the order a walk back from its output
    meets it - so node names and layout never matter.

    Returns:
        (signature tuple, reachable node count, the Principled BSDFs reached)
    """
    output = _output_node(tree, output_kind)
    if output is None:
        return ((), 0, [])

    # socket -> (node, output socket) it is fed from, muted links skipped
    feeds = {}
    for link in tree.links:
        if link.is_muted or not link.is_valid:
            continue
        feeds[link.to_socket.as_pointer()] = (link.from_node, link.from_socket)

    order = {}
    stack = [output]
    while stack:
        node = stack.pop()
        if node in order:
            continue
        # a muted node or reroute passes straight through - still walked
        order[node] = len(order)
        for socket in reversed(node.inputs):
            fed = feeds.get(socket.as_pointer())
            if fed is not None and fed[0] not in order:
                stack.append(fed[0])

    signature = []
    bsdfs = []
    size = 0
    for node in order:
        entry = [node.bl_idname, node.mute, _node_settings(node)]
        inputs = []
        for index, socket in enumerate(node.inputs):
            if not socket.enabled:
                continue
            fed = feeds.get(socket.as_pointer())
            if fed is None:
                inputs.append((index, None))
            else:
                from_node, from_socket = fed
                inputs.append((index, order.get(from_node),
                               list(from_node.outputs).index(from_socket)))
        entry.append(tuple(inputs))
        group = getattr(node, "node_tree", None)
        if group is not None:
            if group not in groups:
                groups[group] = None        # a group inside itself stops here
                groups[group] = _tree_signature(group, "NodeGroupOutput", groups)
            group_signature = groups[group]
            if group_signature is not None:
                entry.append(group_signature[0])
                size += group_signature[1]
                bsdfs.extend(group_signature[2])
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            bsdfs.append((node, feeds))
        signature.append(tuple(entry))
        size += 1
    return (tuple(signature), size, bsdfs)


def _needs_own_depth_passes(mat, bsdfs):
    """True when EEVEE can't draw its shadow and depth with the shared
    opaque shaders."""
    if getattr(mat, "surface_render_method", "DITHERED") == "BLENDED":
        return True
    for node, feeds in bsdfs:
        alpha = node.inputs.get("Alpha")
        if alpha is None:
            continue
        if alpha.as_pointer() in feeds or alpha.default_value < 1.0:
            return True
    return False


def shader_signature(mat, groups=None):
    """(digest, reachable node count, needs its own depth passes) - materials
    with the same digest compile to one shader. None without a node tree."""
    tree = mat.node_tree
    if not mat.use_nodes or tree is None:
        return None
    groups = {} if groups is None else groups
    signature, size, bsdfs = _tree_signature(tree, "ShaderNodeOutputMaterial", groups)
    settings = tuple((key, getattr(mat, key)) for key in _MATERIAL_PROPS
                     if hasattr(mat, key))
    digest = hashlib.sha1(repr((settings, signature)).encode("utf-8")).hexdigest()
    return digest, size, _needs_own_depth_passes(mat, bsdfs)


def shader_report(materials):
    """What a set of materials costs EEVEE to compile.

    Returns:
        dict: materials, shaders (distinct structures), own_depth (shaders
            needing shadow/depth passes of their own), nodes (reachable nodes
            summed over the distinct shaders - roughly the code compiled), and
            largest: [(nodes, how many materials share it, a material's name)]
            for the five biggest shaders.
    """
    groups = {}
    shaders = {}
    count = 0
    for mat in {mat for mat in materials if mat is not None}:
        signature = shader_signature(mat, groups)
        if signature is None:
            continue
        count += 1
        digest, size, own_depth = signature
        entry = shaders.get(digest)
        if entry is None:
            shaders[digest] = [size, own_depth, 1, mat.name]
        else:
            entry[2] += 1
    largest = sorted(shaders.values(), key=lambda entry: -entry[0])[:5]
    return {
        "materials": count,
        "shaders": len(shaders),
        "own_depth": sum(1 for entry in shaders.values() if entry[1]),
        "nodes": sum(entry[0] for entry in shaders.values()),
        "largest": [(size, users, name) for size, _, users, name in largest],
    }


def print_shader_report(materials, prefix="Charon Forge: "):
    report = shader_report(materials)
    print(
        "%sshaders - %d materials compile to ~%d distinct shaders (%d nodes in "
        "all), %d of them with shadow/depth passes of their own; largest: %s"
        % (
            prefix, report["materials"], report["shaders"], report["nodes"],
            report["own_depth"],
            ", ".join("%d nodes x%d (%s)" % entry for entry in report["largest"]) or "-",
        )
    )
    return report
