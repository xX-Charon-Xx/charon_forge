"""What changed between the scene and a build brought back from the game.
Records match on ObjectID, UserData and placement within TOLERANCE; timestamps aren't compared."""

import math

from ..objects.group import Group
from ..objects.part import Part
from ..objects.shapes.forged import Forged

# how far apart two records can be (metres and Up/At components) and still match
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
    """[(object, [record])] for every scene object that saves parts, and the
    oldest Timestamp among plain parts and groups."""
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
    """(game records to import, scene objects changed or deleted in game,
    oldest scene Timestamp) for the scene against the game's parts."""
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
