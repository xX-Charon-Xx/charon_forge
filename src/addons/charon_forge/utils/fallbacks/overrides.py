"""Which part class builds which object id, without the base builder addon's part classes.
Without that addon every part is a plain part; other addons can still register classes."""

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
