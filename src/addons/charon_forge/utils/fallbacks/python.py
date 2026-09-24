"""Plain python helpers - the base builder addon's utils/python.py."""

import json


def load_dictionary(json_path):
    """The dictionary stored in a JSON file."""
    with open(json_path, "r") as stream:
        return json.load(stream)


def get_adjacent_dict_key(data, current, step="next"):
    """The key after (step="next") or before (step="prev") `current` in a
    list of keys, wrapping round at either end."""
    keys = data
    current_index = keys.index(current) if current in keys else 0
    next_index = current_index + 1 if step == "next" else current_index - 1
    if next_index > len(keys) - 1:
        next_index = 0
    if next_index < 0:
        next_index = len(keys) - 1
    return keys[next_index]


def prefer_int(value):
    """The value as an int when it is one, else unchanged."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return value
