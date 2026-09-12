"""Collapsing the datablocks that appending assets duplicates.

Appending is per file, and Blender has no idea that two asset files reference
the same texture on disk or carry the same node group - it just appends both
copies and renames the second one .001. Over a whole base that is the single
biggest source of wasted memory, because textures are ~98% of the scene.

Measured on 100 distinct assets / 6000 placed parts:
  without dedupe   692 images, 67 node groups, 2580 MB, 6.96s to load textures
  with dedupe      333 images,  1 node group,  1092 MB, 2.51s to load textures

So it is worth roughly 2.4x the RAM and 2.8x the texture load time, for about
a second of work at the end of an import. Materials are deliberately left
alone - they are cheap once they share their images, and two same named
materials from different assets are not guaranteed to be identical.
"""

import os

import bpy

from .deferral import should_defer
from .properties import COLOURISE_GROUP


def dedupe_appended_data():
    """Collapse the datablocks the appends duplicated.

    Call this once, after a whole batch of assets is appended, never per asset
    - the cost is one walk over every material node tree, so doing it once for
    100 assets is 100x cheaper than doing it as they arrive.

    Returns:
        tuple: (images removed, node groups removed)
    """
    if should_defer():
        return 0, 0

    image_map = _plan_image_dedupe()
    group_map = _plan_node_group_dedupe()

    if not image_map and not group_map:
        return 0, 0

    _repoint_nodes(image_map, group_map)

    # one batch_remove for both - see _remove_dead
    dead_images = _collect_dead(image_map)
    dead_groups = _collect_dead(group_map)
    bpy.data.batch_remove(dead_images + dead_groups)
    return len(dead_images), len(dead_groups)


def dedupe_images():
    """Collapse image datablocks that point at the same file on disk.

    Returns:
        int: How many duplicate image datablocks were removed.
    """
    image_map = _plan_image_dedupe()
    if not image_map:
        return 0
    _repoint_nodes(image_map, None)
    return _remove_dead(image_map)


def dedupe_node_groups():
    """Collapse every appended copy of the colourise node group into one.

    Every asset file carries its own copy, so appending N assets leaves
    NMS_Colourise.001 ... .00N behind. They are identical by construction.

    Returns:
        int: How many duplicate groups were removed.
    """
    group_map = _plan_node_group_dedupe()
    if not group_map:
        return 0
    _repoint_nodes(None, group_map)
    return _remove_dead(group_map)


def _plan_image_dedupe():
    """Build {duplicate image: canonical image} for images sharing a file."""
    canonical_by_path = {}
    duplicates = {}

    for image in bpy.data.images:
        filepath = image.filepath
        if not filepath:
            continue
        key = os.path.normcase(bpy.path.abspath(filepath))
        canonical = canonical_by_path.get(key)
        if canonical is None:
            canonical_by_path[key] = image
        else:
            duplicates[image] = canonical

    return duplicates


def _plan_node_group_dedupe(prefix=COLOURISE_GROUP):
    """Build {duplicate group: canonical group} for the colourise copies."""
    groups = sorted(
        (group for group in bpy.data.node_groups if group.name.startswith(prefix)),
        key=lambda group: group.name,
    )
    if len(groups) < 2:
        return {}

    canonical = groups[0]
    return {group: canonical for group in groups[1:]}


def _repoint_nodes(image_map, group_map):
    """Swap every duplicate reference in every material for its canonical.

    One pass handles images and node groups together, because the walk itself
    is the expensive part - the node trees of a hundred appended assets are a
    few thousand nodes and every attribute read crosses into Blender.
    """
    for material_data in bpy.data.materials:
        node_tree = material_data.node_tree
        if node_tree is None:
            continue
        for node in node_tree.nodes:
            node_type = node.type
            if image_map and node_type == "TEX_IMAGE":
                canonical = image_map.get(node.image)
                if canonical is not None:
                    node.image = canonical
            elif group_map and node_type == "GROUP":
                canonical = group_map.get(node.node_tree)
                if canonical is not None:
                    node.node_tree = canonical


def _collect_dead(duplicate_map):
    """List the duplicates nothing points at any more.

    Anything the node walk didn't reach - a fake user, a reference from
    somewhere outside the material trees - is handed to user_remap first, so a
    datablock is never dropped while something still needs it.
    """
    dead = []
    for duplicate, canonical in duplicate_map.items():
        if duplicate.users:
            duplicate.user_remap(canonical)
        if duplicate.users == 0:
            dead.append(duplicate)
    return dead


def _remove_dead(duplicate_map):
    """Drop every duplicate nothing points at any more.

    batch_remove() rather than a remove() per datablock: removing one at a time
    rescans the whole file for users each time, which costs 0.54s for the ~400
    duplicates a 100 asset base leaves behind, against 0.006s for the batch.

    Returns:
        int: How many datablocks were removed.
    """
    if not duplicate_map:
        return 0
    dead = _collect_dead(duplicate_map)
    bpy.data.batch_remove(dead)
    return len(dead)
