"""Rebuild a reproducible variant from its root's mesh and the transform in objects_map.json.
The transform is in the asset's own Y-up mesh space."""

import json
import os
import re

import mathutils

RESOURCES_DIR = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "..", "resources")
)

OBJECTS_MAP = os.path.join(RESOURCES_DIR, "objects_map.json")

# keys in the json that are metadata rather than object ids
META_PREFIX = "_"

# wall tier suffix; a variant on a different tier from its root is a different
# mesh, so it is never rebuilt
TIER_SUFFIX = re.compile(r"\((BASE|MID|TOP)\)\s*$")


def _tier(nice_name):
    match = TIER_SUFFIX.search(nice_name or "")
    return match.group(1) if match else None

# {variant id: (root id, 4x4 mesh space matrix)}, built once per session.
_rebuild_table = None


def _build_table():
    """{variant id: (root id, mathutils.Matrix)} from objects_map.json; empty if unreadable."""
    table = {}

    if not os.path.isfile(OBJECTS_MAP):
        return table

    try:
        with open(OBJECTS_MAP, "r") as map_file:
            document = json.load(map_file)
    except (IOError, ValueError):
        return table

    patterns = document.get("%spatterns" % META_PREFIX, {})

    for object_id, record in document.items():
        if object_id.startswith(META_PREFIX):
            continue
        if not record.get("is_variant") or not record.get("reproducible"):
            continue

        # recreate_from: the transform is always measured against the root
        root_id = record.get("recreate_from") or record.get("variant_of")
        pattern = patterns.get(record.get("pattern"))
        if not root_id or pattern is None:
            continue

        root_record = document.get(root_id)
        if root_record is None:
            continue
        if _tier(record.get("nice_name")) != _tier(root_record.get("nice_name")):
            continue

        rotation = pattern.get("matrix")
        if rotation is None:
            continue

        # absent when it is zero
        translation = record.get("translation") or [0.0, 0.0, 0.0]

        matrix = mathutils.Matrix.Identity(4)
        for row in range(3):
            for column in range(3):
                matrix[row][column] = float(rotation[row][column])
            matrix[row][3] = float(translation[row])

        table[object_id] = (root_id, matrix)

    return table


def get_rebuild_table(rebuild=False):
    global _rebuild_table

    if _rebuild_table is None or rebuild:
        _rebuild_table = _build_table()

    return _rebuild_table


def get_rebuild(object_id):
    """(root id, matrix to apply to a copy of the root's mesh), or None when
    the id should use its own asset."""
    return get_rebuild_table().get(object_id.replace("^", ""))
