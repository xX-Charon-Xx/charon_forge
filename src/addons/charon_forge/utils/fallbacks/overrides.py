"""Which part class builds which object id - the base builder addon's
builder/overrides.py, without its part classes.

The special parts (cables, turrets, fossils, message modules) are that
addon's own classes, so without it every part is built as a plain part.
Other addons can still register their own classes here.
"""

_REGISTERED_BY_ID = {}


def register_override(class_ref, object_ids):
    for object_id in object_ids:
        _REGISTERED_BY_ID[object_id.replace("^", "")] = class_ref


def unregister_override(object_ids):
    for object_id in object_ids:
        _REGISTERED_BY_ID.pop(object_id.replace("^", ""), None)


def get_override_class(object_id):
    return _REGISTERED_BY_ID.get(object_id)


def get_part_class(object_id):
    from ...objects.part import Part

    return get_override_class(object_id) or Part
