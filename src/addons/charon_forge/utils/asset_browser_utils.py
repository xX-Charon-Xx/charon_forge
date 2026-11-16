"""Plain data helpers behind the asset browser: preferences, favourites, the category tree.
Most of it runs from draw code, so it returns something usable rather than raising."""

import json
import os
import sys
import tempfile

import bpy

from . import dictionary
from .. import addon_preferences

# the addon key in bpy.context.preferences.addons
ADDON_ID = addon_preferences.ADDON_ID

# how many recently used parts to remember
RECENTS_LIMIT = 60

# used when the preferences cannot be reached
FALLBACK_ICON_SIZE = 3
FALLBACK_COLUMNS = 3

# favourites and recents live in our own file, so they survive reinstalls and
# new Blender versions
APP_DIRECTORY_NAME = "CharonForge"
STORE_DIRECTORY_NAME = "asset_browser"
STORE_FILE_NAME = "asset_browser.json"
STORE_VERSION = 1

# point this at a folder to keep the store somewhere else
DATA_DIRECTORY_ENV = "NMS_BASE_BUILDER_DATA_DIR"

# what the store holds; same names as the old preferences
STORE_KEYS = ("favourite_objects", "favourite_categories", "recent_objects", "category_order")

# cached in memory, re-read only when the file changes on disk
_store_cache = None
_store_mtime = None

# Which preference holds the icon size and column count for each view mode.
GRID_SIZE_PROPERTIES = {
    "Grid": ("asset_browser_icon_size", "asset_browser_number_of_columns"),
    "List": ("asset_browser_icon_size_list", "asset_browser_number_of_columns_list"),
    "Other": ("asset_browser_icon_size_other", "asset_browser_number_of_columns_other"),
}


# --- preferences -------------------------------------------------------------

def get_preferences(context=None):
    """The addon preferences, or None when the addon isn't registered."""
    context = context if context is not None else bpy.context
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon is not None else None


def load_json_preference(name):
    """Read one of the json list preferences; empty if missing or unreadable."""
    prefs = get_preferences()
    if prefs is None:
        return []

    raw = getattr(prefs, name, "")
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return value if isinstance(value, list) else []


def save_preferences():
    """Flush the preferences to disk, ignoring failures."""
    try:
        bpy.ops.wm.save_userpref()
    except RuntimeError:
        pass


def push_recent(recent_ids, object_id, limit=RECENTS_LIMIT):
    """Move `object_id` to the front of a recents list, keeping at most `limit`."""
    entries = [entry for entry in recent_ids if entry != object_id]
    entries.insert(0, object_id)
    return entries[:limit]


# --- the on disk store -------------------------------------------------------

def get_user_data_directory():
    """The per-platform folder for data that outlives the addon (may not exist yet)."""
    override = os.environ.get(DATA_DIRECTORY_ENV)
    if override:
        return override

    if sys.platform == "win32":
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        root = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        root = (os.environ.get("XDG_DATA_HOME")
                or os.path.join(os.path.expanduser("~"), ".local", "share"))

    return os.path.join(root, APP_DIRECTORY_NAME)


def get_store_path():
    """Full path of the asset browser store file."""
    return os.path.join(get_user_data_directory(), STORE_DIRECTORY_NAME,
                        STORE_FILE_NAME)


def _empty_store():
    store = {"version": STORE_VERSION}
    store.update({key: [] for key in STORE_KEYS})
    return store


def _read_store_file(path):
    """Load the store from disk, or None if there is nothing usable there."""
    try:
        with open(path, "r", encoding="utf-8") as store_file:
            data = json.load(store_file)
    except (OSError, json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    # a hand edited or truncated file should not be able to break the browser,
    # so anything that is not a list of strings is quietly dropped
    store = _empty_store()
    for key in STORE_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            store[key] = [entry for entry in value if isinstance(entry, str)]
    return store


def _migrate_from_preferences():
    """Copy favourites and recents over from the old addon preferences, once."""
    store = _empty_store()
    for key in STORE_KEYS:
        store[key] = load_json_preference(key)
    return store


def read_store():
    """The store, from memory when it has not changed on disk."""
    global _store_cache, _store_mtime

    path = get_store_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None

    if _store_cache is not None and mtime == _store_mtime:
        return _store_cache

    store = _read_store_file(path)
    if store is None:
        # nothing on disk yet: either a first run, or an upgrade from the
        # version that kept all this in the preferences
        store = _migrate_from_preferences()
        if any(store[key] for key in STORE_KEYS):
            write_store(store)
            return _store_cache

    _store_cache = store
    _store_mtime = mtime
    return store


def write_store(store):
    """Save the store safely; True if it reached the disk."""
    global _store_cache, _store_mtime

    path = get_store_path()
    directory = os.path.dirname(path)
    temp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        # written beside the real file and moved into place, so a crash part way
        # through cannot leave a half written store behind
        handle, temp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as temp_file:
            json.dump(store, temp_file, indent=2)
        os.replace(temp_path, path)
        temp_path = None
    except OSError as error:
        print("No Man's Sky Base Builder: could not save %s (%s)" % (path, error))
        if temp_path is not None:
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return False

    _store_cache = store
    try:
        _store_mtime = os.path.getmtime(path)
    except OSError:
        _store_mtime = None
    return True


def clear_store_cache():
    """Forget the in-memory copy, so the next read comes off the disk."""
    global _store_cache, _store_mtime
    _store_cache = None
    _store_mtime = None


def load_stored_list(name):
    """A copy of one of the stored lists."""
    return list(read_store().get(name, ()))


def save_stored_list(name, value):
    """Replace one of the stored lists and write the file."""
    store = dict(read_store())
    store[name] = list(value)
    return write_store(store)


def toggle_stored_list(name, value):
    """Add `value` to a stored list, or remove it if already there."""
    entries = load_stored_list(name)
    if value in entries:
        entries.remove(value)
    else:
        entries.append(value)

    save_stored_list(name, entries)
    return entries


# --- grid sizing -------------------------------------------------------------

def get_grid_size_properties(view_mode):
    """The preference names holding the icon size and columns for a view mode."""
    return GRID_SIZE_PROPERTIES.get(view_mode, GRID_SIZE_PROPERTIES["Grid"])


def get_grid_settings(context, icon_size_prop, columns_prop):
    """Icon size and column count, or sane defaults if preferences are missing."""
    prefs = get_preferences(context)
    if prefs is None:
        return FALLBACK_ICON_SIZE, FALLBACK_COLUMNS
    return (getattr(prefs, icon_size_prop, FALLBACK_ICON_SIZE),
            getattr(prefs, columns_prop, FALLBACK_COLUMNS))


# --- the category tree -------------------------------------------------------

def build_category_tree(favourite_ids=None, nice_names=None):
    """The parts definition as {category: {sub category: {object id: part data}}}.
    Variants are folded into their family's root entry."""
    favourite_ids = (favourite_ids if favourite_ids is not None
                     else load_stored_list("favourite_objects"))
    nice_names = (nice_names if nice_names is not None
                  else dictionary.get_nice_names_diictionary())

    categories_list = {}
    part_definition = dictionary.get_parts_definition()
    roots = dictionary.get_variant_roots()

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
        entry["name"] = dictionary.to_title_case(root_part[7] or nice_name)
        entry["is_fav"] = root in favourite_ids

        if object_id != root:
            entry.setdefault("variants", []).append(object_id)

    return categories_list


def order_categories(categories, favourite_categories, stored_order=None):
    """All category names, favourites first, each group in its saved order.
    Categories missing from the saved order are appended."""
    if stored_order is None:
        stored_order = load_stored_list("category_order")

    valid_categories = list(categories)
    valid_set = set(valid_categories)
    favourite_set = set(favourite_categories)

    known_order = [name for name in stored_order if name in valid_set]
    known_set = set(known_order)
    full_order = known_order + [name for name in valid_categories if name not in known_set]

    favourites = [name for name in full_order if name in favourite_set]
    others = [name for name in full_order if name not in favourite_set]
    return favourites + others


def move_category(categories, favourite_categories, category, direction):
    """Move a category up or down within its favourite/other group, and save the order.
    Never moves it across into the other group."""
    order = order_categories(categories, favourite_categories)
    if category not in order:
        return order

    favourite_set = set(favourite_categories)
    is_fav = category in favourite_set
    index = order.index(category)
    target = index + (-1 if direction == "UP" else 1)

    if target < 0 or target >= len(order):
        return order
    if (order[target] in favourite_set) != is_fav:
        return order

    order[index], order[target] = order[target], order[index]
    save_stored_list("category_order", order)
    return order


def build_enum_entries(names):
    """Blender enum entries for a list of names."""
    return [(name, name, name) for name in names]


def build_sub_category_entries(categories_data, category):
    """Sub category enum entries for one category, "All" first."""
    entries = [("All", "All", "All")]
    entries.extend(build_enum_entries(categories_data.get(category, ())))
    return entries


def resolve_sub_categories(categories_data, category, sub_category):
    """The slice of the tree a panel should draw for a selection.
    Copes with stale or empty enum values instead of raising."""
    if not categories_data:
        return {}

    if category not in categories_data:
        # fall back to the first real category rather than showing nothing
        category = next(iter(categories_data))

    sub_categories = categories_data[category]
    if (not sub_category or sub_category == "All"
            or sub_category not in sub_categories):
        return sub_categories

    return {sub_category: sub_categories[sub_category]}


# --- searching and slicing ---------------------------------------------------

def filter_objects(categories_data, search_filter):
    """Parts whose id or name contains `search_filter` (case-insensitive), by category."""
    search_filter = (search_filter or "").strip().lower()
    if not search_filter:
        return {}

    search_results = {}
    for category, sub_categories in categories_data.items():
        for _, objects_list in sub_categories.items():
            for obj_id, obj_data in objects_list.items():

                obj_id_lower = obj_id.lower()
                name_lower = str(obj_data.get("name", "")).lower()

                if search_filter in obj_id_lower or search_filter in name_lower:
                    search_results.setdefault(category, {})[obj_id] = obj_data
    return search_results


def quick_search(categories_data, search_filter, limit=8):
    """The best `limit` parts for a query, and how many matched in all.
    Name prefix matches first, then id prefix, then anything containing it."""
    query = (search_filter or "").strip().lower()
    if not query:
        return {}, 0

    ranked = ([], [], [])
    for sub_categories in categories_data.values():
        for objects_list in sub_categories.values():
            for obj_id, obj_data in objects_list.items():
                name = str(obj_data.get("name", "")).lower()
                object_id = obj_id.lower()
                if name.startswith(query):
                    ranked[0].append((obj_id, obj_data))
                elif object_id.startswith(query):
                    ranked[1].append((obj_id, obj_data))
                elif query in name or query in object_id:
                    ranked[2].append((obj_id, obj_data))

    matches = ranked[0] + ranked[1] + ranked[2]
    return dict(matches[:limit]), len(matches)


def iter_all_parts(categories_data):
    """Every part in the tree, as (object id, part data) pairs."""
    for sub_categories in categories_data.values():
        for objects_list in sub_categories.values():
            for obj_id, obj_data in objects_list.items():
                yield obj_id, obj_data


def apply_favourites(categories_data, favourite_ids):
    """Stamp `is_fav` across the tree and return the favourites."""
    favourites = {}
    for obj_id, obj_data in iter_all_parts(categories_data):
        is_fav = obj_id in favourite_ids
        obj_data["is_fav"] = is_fav
        if is_fav:
            favourites[obj_id] = obj_data
    return favourites


def collect_recent_objects(categories_data, recent_ids):
    """The part data for recently used ids, in order; missing ids are dropped."""
    all_objects = dict(iter_all_parts(categories_data))
    return {obj_id: all_objects[obj_id]
            for obj_id in recent_ids
            if obj_id in all_objects}


def build_presets_data():
    """The presets, shaped like the part entries so the same drawing code works."""
    # imported here rather than at the top: preset pulls in part and the material
    # utils, and this module is imported from inside utils itself
    from ..objects.preset import Preset

    return {
        preset_name: {
            "name": preset_name,
            "link": preset_link,
            "is_preset": True,
        }
        for preset_name, preset_link in Preset.get_presets().items()
    }
