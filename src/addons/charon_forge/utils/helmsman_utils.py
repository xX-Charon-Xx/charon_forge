"""The batch ship list the helmsman panel loads, and the results it writes.

Split out the same way optimiser_utils.py is: this is entirely about the
batch format, nothing Blender specific.

A batch is a JSON array, from the clipboard or a .json/.txt file:

    [{
      "id": "9f34d533-...-1fa5a26610d2",
      "name": "TYN | Drake Golem MK-3",
      "part_count": 844,
      "objects": [ ...the ship's parts... ],
      "approval_status": "pending",
      "note": ""
    }, ...]

"objects" is the ship's parts English keyed (ObjectID/Position/Up/At/
Timestamp/UserData) - the shape save_translation.translate_to_obf_data
expects, so it can go straight into a save file without reshaping.
"""

import json

# What a review row's slot sits on when the save has no corvette left for
# it - see helmsman.get_slot_enum_items. Here rather than in helmsman.py so
# helmsman_presentation.py can read it too without importing helmsman.py,
# which imports it back.
NO_SLOT_ID = "NONE"
NO_SLOT_LABEL = "None"

# approval_status in the batch <-> BatchShipReviewItem.review_status
APPROVAL_TO_REVIEW = {"approved": "APPROVE", "rejected": "REJECT", "pending": "PENDING"}
REVIEW_TO_APPROVAL = {"APPROVE": "approved", "REJECT": "rejected"}

# how many problems a failed validation lists before "and N more"
MAX_REPORTED_ERRORS = 5


class BatchError(ValueError):
    """The batch text is not a valid ship list; str() says why."""


def _ship_label(index, ship):
    name = ship.get("name") if isinstance(ship, dict) else None
    return f"ship {index + 1}" + (f" ({name})" if isinstance(name, str) and name else "")


def _validate_ship(index, ship, errors):
    label = _ship_label(index, ship)
    if not isinstance(ship, dict):
        errors.append(f"{label}: is not an object")
        return

    for key in ("id", "name"):
        value = ship.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label}: \"{key}\" must be a non-empty string")

    objects = ship.get("objects")
    if not isinstance(objects, list):
        errors.append(f"{label}: \"objects\" must be an array")
    else:
        for part_index, part in enumerate(objects):
            if not isinstance(part, dict) or not isinstance(part.get("ObjectID"), str):
                errors.append(f"{label}: object {part_index + 1} has no \"ObjectID\"")
                break

    part_count = ship.get("part_count")
    if part_count is not None and (isinstance(part_count, bool) or not isinstance(part_count, int)):
        errors.append(f"{label}: \"part_count\" must be a whole number")

    status = ship.get("approval_status", "pending")
    if status not in APPROVAL_TO_REVIEW:
        errors.append(
            f"{label}: \"approval_status\" must be one of "
            + ", ".join(f'"{key}"' for key in APPROVAL_TO_REVIEW)
        )

    note = ship.get("note", "")
    if not isinstance(note, str):
        errors.append(f"{label}: \"note\" must be a string")


def parse_batch(text):
    """The ships in a batch, validated.

    Args:
        text (str): The clipboard or file contents.

    Returns:
        list: The batch's ship dicts, exactly as given.

    Raises:
        BatchError: What is wrong with it, naming the ships and fields.
    """
    if not text or not text.strip():
        raise BatchError("it is empty")

    try:
        data = json.loads(text)
    except ValueError as error:
        raise BatchError(f"it is not valid JSON ({error})") from None

    if not isinstance(data, list):
        raise BatchError("it must be a JSON array of ships")
    if not data:
        raise BatchError("it holds no ships")

    errors = []
    seen_ids = {}
    for index, ship in enumerate(data):
        _validate_ship(index, ship, errors)
        ship_id = ship.get("id") if isinstance(ship, dict) else None
        if isinstance(ship_id, str) and ship_id:
            if ship_id in seen_ids:
                errors.append(
                    f"{_ship_label(index, ship)}: same \"id\" as ship {seen_ids[ship_id] + 1}"
                )
            else:
                seen_ids[ship_id] = index

    if errors:
        shown = errors[:MAX_REPORTED_ERRORS]
        more = len(errors) - len(shown)
        raise BatchError("; ".join(shown) + (f"; and {more} more" if more else ""))
    return data


def get_review_status(ship):
    """The review_status a row starts on, from the ship's approval_status."""
    return APPROVAL_TO_REVIEW.get(ship.get("approval_status", "pending"), "PENDING")


def build_results(rows):
    """The review results as a batch, for Export to clipboard/file.

    Args:
        rows: (ship dict, review_status, note) for every row, in list order.

    Returns:
        list: The approved and rejected ships only, each as
            {"id", "approval_status"} plus "note" when one was written.
            Pending ships are left out entirely.
    """
    results = []
    for ship, review_status, note in rows:
        status = REVIEW_TO_APPROVAL.get(review_status)
        if status is None:
            continue
        result = {"id": ship["id"], "approval_status": status}
        note = (note or "").strip()
        if note:
            result["note"] = note
        results.append(result)
    return results


def dump_results(results):
    return json.dumps(results, indent=2, ensure_ascii=False)
