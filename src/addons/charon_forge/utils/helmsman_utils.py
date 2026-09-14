"""The batch ship list the helmsman panel's Import Batch button reads.

Split out the same way optimiser_utils.py is: this is entirely about where
the batch file lives on disk and its shape, nothing Blender specific.
"""

import json
import os

RESOURCES_DIR = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "..", "resources")
)

BATCH_SHIP_JSON = os.path.join(RESOURCES_DIR, "batch_ship_test.json")

# What a review row's slot sits on when the save has no corvette left for
# it - see helmsman.get_slot_enum_items. Here rather than in helmsman.py so
# helmsman_presentation.py can read it too without importing helmsman.py,
# which imports it back.
NO_SLOT_ID = "NONE"
NO_SLOT_LABEL = "No Slot Available"


def get_batch_ships():
    """[{"name": str, "part_count": int, "objects": list}, ...].

    "objects" is the ship's parts exactly as they sit in the file, English
    keyed (ObjectID/Position/Up/At/Timestamp/UserData) - the shape the host
    addon's save_translation.translate_to_obf_data expects, so it can go
    straight into a save file without reshaping. See
    helmsman_operators.ExportToSave.

    Read fresh rather than cached: the Import Batch button is a deliberate,
    infrequent click rather than something a panel redraws constantly, so
    there is no draw-time cost to avoid the way get_cached_priority_list's is.
    """
    try:
        with open(BATCH_SHIP_JSON, "r", encoding="utf-8") as batch_file:
            data = json.load(batch_file)
    except (OSError, json.JSONDecodeError, ValueError):
        return []

    if not isinstance(data, list):
        return []

    ships = []
    for ship in data:
        if not isinstance(ship, dict):
            continue
        objects = ship.get("Objects")
        objects = objects if isinstance(objects, list) else []
        ships.append({
            "name": ship.get("Name") or "Unnamed Ship",
            "part_count": len(objects),
            "objects": objects,
        })
    return ships
