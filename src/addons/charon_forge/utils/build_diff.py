"""What changed between the scene and a build brought back from the game.

The scene and the game's parts are matched record for record: two records
are the same part when their ObjectID and UserData match and they sit in the
same place, facing the same way, within TOLERANCE. Timestamps are not
compared - a Forge shape stamps its parts with the time of the export, so
the game's copies carry a different one than the scene would give them now.

- A game record with no match in the scene was placed or changed in game.
  It counts only when its Timestamp is no older than the scene's oldest part,
  so a scene holding one piece of a bigger base doesn't pull the rest in.
- A scene object with a record that has no match in the game was changed or
  deleted in game. A group or Forge shape counts when any one of its parts has.
"""

import math

from ..objects.group import Group
from ..objects.part import Part
from ..objects.shapes.forged import Forged

# how far apart, in metres and in Up/At components, two records can be and
# still be the same part - well above the float noise of a round trip through
# Blender and the game, well below any move made on purpose
TOLERANCE = 0.01

# the side of a cell in the spatial lookup; a match is always in the record's
# own cell or one next to it, as long as this is bigger than TOLERANCE
_CELL = 1.0


def _object_id(record):
    return str(record.get(Part.PROP_OBJECT_ID, "")).replace("^", "")


def _user_data(record):
    try:
        return int(record.get(Part.PROP_USER_DATA, 0))
    except (TypeError, ValueError):
        return 0


def _timestamp(record):
    try:
        return int(record.get(Part.PROP_TIMESTAMP))
    except (TypeError, ValueError):
        return None


def _vector(record, key):
    value = record.get(key) or (0.0, 0.0, 0.0)
    try:
        return tuple(float(value[axis]) for axis in range(3))
    except (TypeError, ValueError, IndexError):
        return (0.0, 0.0, 0.0)


def _cell(position):
    return tuple(math.floor(axis / _CELL) for axis in position)


def _close(first, second):
    return all(abs(a - b) <= TOLERANCE for a, b in zip(first, second))


class _SceneIndex(object):
    """The scene's records, looked up by id, colour and cell."""

    def __init__(self):
        # (object id, user data, cell) -> [entry], an entry being
        # [position, up, at, owner, matched]
        self._cells = {}
        self.entries = []

    def add(self, record, owner):
        position = _vector(record, Part.PROP_POSITION)
        entry = [
            position,
            _vector(record, Part.PROP_UP),
            _vector(record, Part.PROP_AT),
            owner,
            False,
        ]
        key = (_object_id(record), _user_data(record), _cell(position))
        self._cells.setdefault(key, []).append(entry)
        self.entries.append(entry)

    def claim(self, record):
        """Mark the scene record matching this one as found. False when
        there is none left to match."""
        object_id, user_data = _object_id(record), _user_data(record)
        position = _vector(record, Part.PROP_POSITION)
        up = _vector(record, Part.PROP_UP)
        at = _vector(record, Part.PROP_AT)
        cx, cy, cz = _cell(position)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for entry in self._cells.get((object_id, user_data, (cx + dx, cy + dy, cz + dz)), ()):
                        if entry[4]:
                            continue
                        if _close(entry[0], position) and _close(entry[1], up) and _close(entry[2], at):
                            entry[4] = True
                            return True
        return False


def _as_list(serialised):
    if serialised is None:
        return []
    if isinstance(serialised, dict):
        return [serialised]
    return list(serialised)


def scene_records(builder):
    """Every scene object that saves parts, with the records it saves.

    Returns:
        (list, int or None): [(object, [record])], and the oldest Timestamp
            among plain parts and groups - Forge shapes stamp theirs with
            the time they are saved, so they would always read as new.
    """
    owners = []
    oldest = None

    def note_oldest(records):
        nonlocal oldest
        for record in records:
            stamp = _timestamp(record)
            if stamp is not None and (oldest is None or stamp < oldest):
                oldest = stamp

    for bpy_object in builder.get_all_parts():
        use_class = builder.get_part_class(bpy_object["ObjectID"])
        try:
            records = _as_list(
                use_class.deserialise_from_object(bpy_object, builder_object=builder).serialise()
            )
        except Exception as error:                        # noqa: BLE001
            print("Charon Forge: could not read %s for the diff: %s" % (bpy_object.name, error))
            continue
        note_oldest(records)
        owners.append((bpy_object, records))

    for group_obj in builder.get_all_groups():
        if Forged.is_forged(group_obj):
            continue
        records = _as_list(Group.serialise(group_obj))
        note_oldest(records)
        owners.append((group_obj, records))

    for forged_obj in Forged.get_all():
        owners.append((forged_obj, _as_list(Forged.serialise(forged_obj))))

    return owners, oldest


def diff(builder, game_records):
    """Compare the scene with the game's parts.

    Returns:
        (list, list, int or None): the game records that are new or changed
            and should be imported, the scene objects changed or deleted in
            game, and the oldest scene Timestamp used to leave older parts out.
    """
    owners, oldest = scene_records(builder)

    index = _SceneIndex()
    for owner, records in owners:
        for record in records:
            index.add(record, owner)

    incoming = []
    for record in game_records:
        if index.claim(record):
            continue
        stamp = _timestamp(record)
        if oldest is not None and stamp is not None and stamp < oldest:
            continue
        incoming.append(record)

    changed = []
    seen = set()
    for entry in index.entries:
        owner = entry[3]
        if entry[4] or owner.name in seen:
            continue
        seen.add(owner.name)
        changed.append(owner)

    return incoming, changed, oldest
