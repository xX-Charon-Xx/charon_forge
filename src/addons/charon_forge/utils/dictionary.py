"""Human readable names and categories for object ids."""

import csv
import os
import re

from .base_builder_utils import python_utils

RESOURCES_DIR = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "..", "resources")
)

NICE_JSON = os.path.join(RESOURCES_DIR, "nice_names.json")
nice_name_dictionary = {}

PART_DEFINITION = os.path.join(RESOURCES_DIR, "DT_PartDefinition.csv")
part_definition_dictionary = {}


def to_title_case(text):
    parts = re.split(r'(\([^)]*\))', text)
    return ''.join(
        part if part.startswith('(') else part.title()
        for part in parts
    )


def get_nice_names_diictionary():
    """{object id: nice name}, read from nice_names.json on first use.
    Lazy, as the base builder addon may not be loaded yet at import time."""
    global nice_name_dictionary

    if not nice_name_dictionary:
        nice_name_dictionary = python_utils.load_dictionary(NICE_JSON)

    return nice_name_dictionary


def get_parts_definition():
    """{object id: csv row}, read from DT_PartDefinition.csv on first use."""
    global part_definition_dictionary

    if not part_definition_dictionary:
        with open(PART_DEFINITION, "r", encoding="utf-16") as csv_file:
            csv_reader = csv.reader((x.replace("\0", "") for x in csv_file), delimiter=",")
            for index, row in enumerate(csv_reader):
                if not row or index == 0:
                    continue

                m_obj_id = row[0]
                part_definition_dictionary[m_obj_id] = row

    return part_definition_dictionary


def export_object_id(row_id):
    """The object id a row exports as: its own id, or for an alternate form
    (B_HAB_A_OPEN) the base id from its 13th column."""
    row_id = row_id.replace("^", "")
    row = get_parts_definition().get("^" + row_id)
    if row is not None and len(row) > 12 and row[12].strip():
        return row[12].strip().replace("^", "")
    return row_id


# a nice name's trailing "(NE)", "(Y_NW3)"... that sets family members apart
_NAME_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")

_variant_roots = None


def _base_name(nice_name):
    return _NAME_SUFFIX.sub("", nice_name or "").strip().upper()


def get_variant_roots():
    """{object id: its family's root id}; follows VariantOf chains to the end
    and folds a mirror twin root of the same name into one (NE takes NW)."""
    global _variant_roots
    if _variant_roots is not None:
        return _variant_roots

    part_definition = get_parts_definition()
    variant_of = {}
    names = {}
    for part in part_definition.values():
        object_id = part[0].replace("^", "")
        if not object_id:
            continue
        parent = part[9].replace("^", "")
        variant_of[object_id] = None if parent in ("None", "", object_id) else parent
        names[object_id] = part[7]

    def follow(object_id):
        seen = set()
        while variant_of.get(object_id) and object_id not in seen:
            seen.add(object_id)
            parent = variant_of[object_id]
            if parent not in variant_of:
                break               # names a part that isn't defined
            object_id = parent
        return object_id

    roots = {object_id: follow(object_id) for object_id in variant_of}

    # imported here: the part module is heavy, and this runs once
    from ..objects.part import Part
    merged = {}
    for root in set(roots.values()):
        twin = Part.get_mirror_part_id(root)
        if (twin and twin != root and roots.get(twin) == twin
                and _base_name(names.get(root)) == _base_name(names.get(twin))):
            keep, fold = sorted((root, twin))
            merged[fold] = keep

    _variant_roots = {
        object_id: merged.get(root, root) for object_id, root in roots.items()
    }
    return _variant_roots


_variant_families = None


def get_variant_family(object_id):
    """Buildable members of `object_id`'s family, root first.
    [object_id] when it has no variants, [] when it isn't a part."""
    global _variant_families
    if _variant_families is None:
        nice_names = get_nice_names_diictionary()
        families = {}
        for member, root in get_variant_roots().items():
            if member in nice_names:
                families.setdefault(root, []).append(member)
        for root, members in families.items():
            if root in members:
                members.remove(root)
                members.insert(0, root)
        _variant_families = families

    object_id = (object_id or "").replace("^", "")
    root = get_variant_roots().get(object_id)
    if root is None:
        return []
    return list(_variant_families.get(root) or [object_id])


def get_category_vise_objects():
    """Object ids grouped by category/sub-category, variants nested under
    the object id they are a variant of."""
    categories_list = {}
    part_definition = get_parts_definition()
    nice_names = get_nice_names_diictionary()

    roots = get_variant_roots()

    for _, part in part_definition.items():
        object_id = part[0].replace("^", "")
        nice_name = part[7]

        if not object_id or not nice_name:
            continue

        if object_id not in nice_names:
            continue

        # a family sits under its root's category, with the root's name
        root = roots.get(object_id, object_id)
        root_part = part_definition.get("^" + root) or part_definition.get(root) or part
        category = root_part[2]
        sub_category = root_part[4]

        sub_cat = categories_list.setdefault(category, {}).setdefault(sub_category, {})
        entry = sub_cat.setdefault(root, {})
        entry["name"] = to_title_case(root_part[7] or nice_name)

        if object_id != root:
            entry.setdefault("variants", []).append(object_id)

    return categories_list
