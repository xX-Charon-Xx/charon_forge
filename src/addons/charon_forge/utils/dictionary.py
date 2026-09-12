"""Human readable names and categories for object ids.

Ported from the reference addon's utils/dictionary.py. No host equivalent -
that addon reads its own nice_names.json inline in part.py/group.py rather
than through a dedicated module, so this stays Charon's own code.
"""

import csv
import json
import os
import re
import tempfile

from .base_builder_utils import python_utils

RESOURCES_DIR = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "..", "resources")
)

NICE_JSON = os.path.join(RESOURCES_DIR, "nice_names.json")
nice_name_dictionary = {}

PART_DEFINITION = os.path.join(RESOURCES_DIR, "DT_PartDefinition.csv")
part_definition_dictionary = {}

PRIORITY_LIST_JSON = os.path.join(RESOURCES_DIR, "priority_list.json")
USER_PRIORITY_DIRECTORY_NAME = "optimiser"
USER_PRIORITY_FILE_NAME = "priority_list.json"


def to_title_case(text):
    parts = re.split(r'(\([^)]*\))', text)
    return ''.join(
        part if part.startswith('(') else part.title()
        for part in parts
    )


def get_nice_names_diictionary():
    """{object id: nice name}, read from nice_names.json on first use.

    Loaded lazily rather than at import time: python_utils resolves against
    the base builder addon at call time (see base_builder_utils.py), which is
    not guaranteed to be loaded yet while blender is still importing addons.
    """
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


def get_user_priority_list_path():
    """Where the user's edited copy of the priority list lives.

    Beside the asset browser's store rather than in the addon folder, for the
    same reason: resources/priority_list.json ships with the addon and is
    replaced wholesale on every update, so edits kept there would not survive
    one. See asset_browser_utils.get_user_data_directory.
    """
    from . import asset_browser_utils

    return os.path.join(
        asset_browser_utils.get_user_data_directory(),
        USER_PRIORITY_DIRECTORY_NAME,
        USER_PRIORITY_FILE_NAME,
    )


def _read_priority_list(path):
    """The array of groups in a priority list file, or None if unusable."""
    try:
        with open(path, "r", encoding="utf-8") as priority_file:
            data = json.load(priority_file)
    except (OSError, json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, list):
        return None

    # a hand edited file should not be able to break the panel
    return [group for group in data if isinstance(group, dict)]


def get_priority_list():
    """[{object id: nice name}, ...] - the user's copy, else the shipped one.

    Read fresh rather than cached like the dictionaries above: the optimiser
    panel edits this (reordering/deleting groups) and every read has to see
    the latest write.
    """
    user_list = _read_priority_list(get_user_priority_list_path())
    if user_list is not None:
        return user_list

    shipped_list = _read_priority_list(PRIORITY_LIST_JSON)
    return shipped_list if shipped_list is not None else []


_priority_cache = None
_priority_cache_key = None


def _priority_cache_stamp(path):
    """(path, mtime, size) for a file, or None when it is not there."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (path, stat.st_mtime, stat.st_size)


def get_cached_priority_list():
    """get_priority_list, but cheap enough to call from a panel's draw.

    A panel redraws constantly, so the file is only re-read when its
    timestamp or size actually changes - including when a save swaps the
    shipped default for the user's copy.
    """
    global _priority_cache, _priority_cache_key

    key = (
        _priority_cache_stamp(get_user_priority_list_path())
        or _priority_cache_stamp(PRIORITY_LIST_JSON)
    )
    if _priority_cache is None or key != _priority_cache_key:
        _priority_cache = get_priority_list()
        _priority_cache_key = key

    return _priority_cache


def clear_priority_cache():
    """Forget the in-memory copy, so the next read comes off the disk."""
    global _priority_cache, _priority_cache_key
    _priority_cache = None
    _priority_cache_key = None


def save_priority_list(priority_list):
    """Write the user's copy out, leaving the shipped resource untouched.

    Written to a temporary file and moved into place, so a crash part way
    through cannot leave a half written list behind.

    Returns:
        bool: True if it reached the disk.
    """
    clear_priority_cache()

    path = get_user_priority_list_path()
    directory = os.path.dirname(path)
    temp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        handle, temp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as temp_file:
            json.dump(priority_list, temp_file, indent=4, ensure_ascii=False)
        os.replace(temp_path, path)
        temp_path = None
    except OSError as error:
        print("Charon Forge: could not save %s (%s)" % (path, error))
        if temp_path is not None:
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return False

    return True


def reset_priority_list():
    """Drop the user's copy, so the shipped list is used again."""
    clear_priority_cache()
    try:
        os.remove(get_user_priority_list_path())
    except OSError:
        pass


def get_category_vise_objects():
    """Object ids grouped by category/sub-category, variants nested under
    the object id they are a variant of."""
    categories_list = {}
    part_definition = get_parts_definition()
    nice_names = get_nice_names_diictionary()

    for _, part in part_definition.items():
        object_id = part[0].replace("^", "")
        category = part[2]
        sub_category = part[4]
        nice_name = part[7]
        variant_of = part[9].replace("^", "")

        if not object_id or not nice_name:
            continue

        if object_id not in nice_names:
            continue

        nice_name = to_title_case(nice_name)

        if category not in categories_list:
            categories_list[category] = {}
        if sub_category not in categories_list[category]:
            categories_list[category][sub_category] = {}

        sub_cat = categories_list[category][sub_category]

        if variant_of == "None":
            if object_id not in sub_cat:
                sub_cat[object_id] = {}

            sub_cat[object_id]["name"] = nice_name

        else:
            if variant_of not in sub_cat:
                sub_cat[variant_of] = {
                    "name": nice_name
                }

            if "variants" not in sub_cat[variant_of]:
                sub_cat[variant_of]["variants"] = []
            sub_cat[variant_of]["variants"].append(object_id)

    return categories_list
