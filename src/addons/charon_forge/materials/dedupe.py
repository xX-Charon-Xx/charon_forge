"""Collapsing the images and node groups that appending assets duplicates
(about 2.4x less RAM on a big base). Materials are left alone."""

import os

import bpy

from .deferral import should_defer
from .properties import COLOURISE_GROUP


def dedupe_appended_data():
    """Collapse the duplicated datablocks; call once per batch, not per asset.
    Returns (images removed, node groups removed)."""
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
    """Collapse images that point at the same file. Returns how many were removed."""
    image_map = _plan_image_dedupe()
    if not image_map:
        return 0
    _repoint_nodes(image_map, None)
    return _remove_dead(image_map)


def dedupe_node_groups():
    """Collapse every appended copy of the colourise node group into one.
    Returns how many were removed."""
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
    """Swap every duplicate reference in every material for its canonical,
    images and node groups in one walk."""
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
    """List the duplicates nothing points at any more, remapping any users the
    node walk missed first."""
    dead = []
    for duplicate, canonical in duplicate_map.items():
        if duplicate.users:
            duplicate.user_remap(canonical)
        if duplicate.users == 0:
            dead.append(duplicate)
    return dead


def _remove_dead(duplicate_map):
    """Drop every unused duplicate in one batch_remove (far faster than one at a
    time). Returns how many were removed."""
    if not duplicate_map:
        return 0
    dead = _collect_dead(duplicate_map)
    bpy.data.batch_remove(dead)
    return len(dead)
