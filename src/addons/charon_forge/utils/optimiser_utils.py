"""The priority list the optimiser panel reads, edits and persists.

Split out of dictionary.py - that module is general object id lookups
(nice names, categories), this one is entirely about the priority list
feature: where it lives on disk, its group shape, and the user's edits to it.
"""

import json
import os
import tempfile

import bpy

RESOURCES_DIR = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "..", "resources")
)

PRIORITY_LIST_JSON = os.path.join(RESOURCES_DIR, "priority_list.json")
# what an entry saved without a name shows as
UNNAMED_GROUP_NAME = "Unnamed Group"
USER_PRIORITY_DIRECTORY_NAME = "optimiser"
USER_PRIORITY_FILE_NAME = "priority_list.json"


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

    # a hand edited file should not be able to break the panel, so anything
    # that is not a usable entry is dropped and a missing name/parts is
    # filled in rather than left for the caller to trip over
    groups = []
    for group in data:
        if not isinstance(group, dict):
            continue
        parts = group.get("parts")
        groups.append({
            "name": group.get("name") or UNNAMED_GROUP_NAME,
            "parts": parts if isinstance(parts, dict) else {},
        })
    return groups


def get_priority_list():
    """[{"name": str, "parts": {object id: nice name}}, ...].

    The user's copy, else the shipped one.

    Read fresh rather than cached: the optimiser panel edits this
    (reordering/deleting groups) and every read has to see the latest write.
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


def get_group_name(group):
    """The display name of one priority group."""
    return group.get("name") or UNNAMED_GROUP_NAME


def get_group_parts(group):
    """{object id: nice name} for one priority group."""
    parts = group.get("parts")
    return parts if isinstance(parts, dict) else {}


def new_priority_group(name=UNNAMED_GROUP_NAME):
    """A fresh, empty priority group."""
    return {"name": name, "parts": {}}


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


# Ordering ---
#
# A part's "order" is its position in the saved Objects list. Parts whose
# ObjectID is in the priority list go first, in the list's own order - group
# by group, and part by part inside a group - and every other part comes
# after all of them. Parts that tie keep the order they already had.


def _strip_id(object_id):
    return str(object_id or "").replace("^", "")


def get_priority_ranks():
    """{object id without "^": rank}, lowest first, from the priority list."""
    ranks = {}
    for group in get_priority_list():
        for object_id in get_group_parts(group):
            ranks.setdefault(_strip_id(object_id), len(ranks))
    return ranks


def _rank_key(ranks, object_id):
    """Sort key: the part's rank, or after every ranked part."""
    return ranks.get(_strip_id(object_id), len(ranks))


# The primary corvette parts ---
# A ship can have more than one cockpit or landing bay; the one picked in the
# optimiser panel (scene.charon_optimiser) goes ahead of the others of its
# kind, so the game takes it as the ship's own.

def get_primary_parts():
    """The cockpit and landing bay picked as primary, while the option is on
    - leaving out any empty pick, and any part deleted or no longer in the
    scene."""
    scene = bpy.context.scene
    optimiser = getattr(scene, "charon_optimiser", None)
    if optimiser is None or not optimiser.use_primary_parts:
        return []
    primaries = []
    for obj in (optimiser.cockpit, optimiser.landing_bay):
        try:
            if obj is not None and scene.objects.get(obj.name) is obj:
                primaries.append(obj)
        except ReferenceError:
            continue
    return primaries


# what the parts definition calls them: B_COK_A..., B_ALK_A, B_ALK_A_OPEN...
COCKPIT_PREFIX = "B_COK_"
LANDING_BAY_PREFIX = "B_ALK_"


def mark_primary_parts(objects):
    """Pick the cockpit and landing bay with the lowest order among `objects`
    as the ship's primary ones, and switch the option on.

    Called after an import with the parts it built: the save lists the
    ship's own cockpit and landing bay first, so the lowest order is the one
    the game treats as primary. A kind the import has none of keeps whatever
    was picked before.

    Returns:
        tuple: (cockpit, landing bay) picked, either None.
    """
    optimiser = getattr(bpy.context.scene, "charon_optimiser", None)
    if optimiser is None:
        return None, None

    def lowest(prefix):
        found = []
        for obj in objects:
            try:
                object_id = _strip_id(obj.get("ObjectID") or "")
            except ReferenceError:
                continue
            if object_id.startswith(prefix):
                found.append(obj)
        return min(found, key=lambda obj: obj.get("order", 0), default=None)

    cockpit = lowest(COCKPIT_PREFIX)
    landing_bay = lowest(LANDING_BAY_PREFIX)
    if cockpit is not None:
        optimiser.cockpit = cockpit
    if landing_bay is not None:
        optimiser.landing_bay = landing_bay
    if cockpit is not None or landing_bay is not None:
        optimiser.use_primary_parts = True
    return cockpit, landing_bay


def mark_primary_if_first(bpy_object):
    """Make a newly placed cockpit or landing bay the primary one when it is
    the only one of its kind in the scene - the first placed of each kind is
    the ship's own until the user picks another.

    Returns:
        str: "cockpit" or "landing_bay" when it was marked, else None.
    """
    scene = bpy.context.scene
    optimiser = getattr(scene, "charon_optimiser", None)
    if optimiser is None or bpy_object is None:
        return None

    object_id = _strip_id(bpy_object.get("ObjectID") or "")
    for prefix, slot in ((COCKPIT_PREFIX, "cockpit"), (LANDING_BAY_PREFIX, "landing_bay")):
        if not object_id.startswith(prefix):
            continue
        others = [
            obj for obj in scene.objects
            if obj is not bpy_object
            and _strip_id(obj.get("ObjectID") or "").startswith(prefix)
        ]
        if others:
            return None
        setattr(optimiser, slot, bpy_object)
        optimiser.use_primary_parts = True
        return slot
    return None


def _position_key(object_id, position):
    """What a part is recognised by once serialised: its id and where it is."""
    return _strip_id(object_id), tuple(round(float(value), 3) for value in position)


def _primary_keys(primaries):
    keys = set()
    for obj in primaries:
        object_id = obj.get("ObjectID")
        if object_id:
            # a part is serialised in the game's Y-up space - Blender's
            # position turned -90 degrees about X (Group.extract_pos_up_at)
            x, y, z = obj.matrix_world.translation
            keys.add(_position_key(object_id, (x, z, -y)))
    return keys


def is_auto_optimise_on():
    from ..addon_preferences import get_addon_preferences

    prefs = get_addon_preferences()
    return bool(prefs is not None and prefs.auto_optimise)


def reorder_scene_objects(builder, ranks=None):
    """Renumber every part's "order" so priority parts come first.

    Args:
        builder: The builder to read the scene's parts through.
        ranks (dict): From get_priority_ranks(), to save reading it twice.

    Returns:
        int: How many parts were renumbered.
    """
    ranks = get_priority_ranks() if ranks is None else ranks
    primaries = {obj.as_pointer() for obj in get_primary_parts()}
    # already sorted by their current order, and sorted() is stable, so
    # parts of the same rank keep their relative order - except a primary
    # part, which goes ahead of the rest of its rank
    parts = builder.get_all_parts(include_lines=True)
    parts = sorted(
        parts, key=lambda obj: (
            _rank_key(ranks, obj.get("ObjectID") or obj.get("SnapID")),
            0 if obj.as_pointer() in primaries else 1,
        )
    )
    for order, obj in enumerate(parts):
        if obj.get("order") != order:
            obj["order"] = order
    return len(parts)


def sort_serialised_objects(object_list, ranks=None):
    """Sort serialised part dicts the same way, in place.

    Group members are serialised after every loose part, so reordering the
    scene alone would still leave a priority part inside a group behind
    loose parts that are not in the priority list.
    """
    ranks = get_priority_ranks() if ranks is None else ranks
    primaries = _primary_keys(get_primary_parts())

    def is_primary(data):
        position = data.get("Position")
        if not primaries or not position:
            return False
        return _position_key(data.get("ObjectID"), position) in primaries

    object_list.sort(key=lambda data: (
        _rank_key(ranks, data.get("ObjectID")),
        0 if is_primary(data) else 1,
    ))
    return object_list
