"""Reading and writing ship files: .nmsship (a zip of objects.json, so.json and
ccd.json) and plain .json/.txt parts. Nothing Blender specific."""

import json
import os
import random
import zipfile

OBJECTS_FILE = "objects.json"
SHIP_FILE = "so.json"
CUSTOMISATION_FILE = "ccd.json"

TEMPLATE_JSON = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "..", "resources", "nmsship_template.json"
)


# The BaseVersion used when a file doesn't say, the one serialise() writes;
# below 5 the builder places parts with the older orientation
DEFAULT_BASE_VERSION = 8

FORMAT_NMSSHIP = "NMSSHIP"
FORMAT_JSON = "JSON"
EXTENSIONS = {FORMAT_NMSSHIP: ".nmsship", FORMAT_JSON: ".json"}

# how many bad parts a failed validation lists before "and N more"
MAX_REPORTED_ERRORS = 5


class NmsShipError(ValueError):
    """The file is not a usable ship file; str() says why."""


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_vector(value):
    return isinstance(value, list) and len(value) == 3 and all(_is_number(v) for v in value)


def validate_parts(parts, source):
    """Check a parts list is something the builder can place.
    Raises NmsShipError naming the parts and fields at fault."""
    if not isinstance(parts, list):
        raise NmsShipError(f"{source} must be an array of parts")
    if not parts:
        raise NmsShipError(f"{source} holds no parts")

    errors = []
    for index, part in enumerate(parts):
        label = f"part {index + 1}"
        if not isinstance(part, dict):
            errors.append(f"{label} is not an object")
            continue
        object_id = part.get("ObjectID")
        if not isinstance(object_id, str) or not object_id.strip("^"):
            errors.append(f"{label} has no ObjectID")
        else:
            label += f" ({object_id})"
        for key in ("Position", "Up", "At"):
            if not _is_vector(part.get(key)):
                errors.append(f"{label}: \"{key}\" must be three numbers")
        for key in ("Timestamp", "UserData"):
            value = part.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                errors.append(f"{label}: \"{key}\" must be a whole number")
        if "Message" in part and not isinstance(part["Message"], str):
            errors.append(f"{label}: \"Message\" must be text")
        if len(errors) > MAX_REPORTED_ERRORS:
            break

    if errors:
        shown = errors[:MAX_REPORTED_ERRORS]
        more = len(errors) - len(shown)
        raise NmsShipError(
            f"{source}: " + "; ".join(shown) + ("; and more" if more else "")
        )


def _read_json(archive, name):
    try:
        raw = archive.read(name)
    except KeyError:
        raise NmsShipError(f"it has no {name}") from None
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as error:
        raise NmsShipError(f"{name} is not valid JSON ({error})") from None


def read(path):
    """The parts, ship record (so.json) and customisation (ccd.json) of a .nmsship,
    validated. Raises NmsShipError."""
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as error:
        raise NmsShipError(f"it is not a .nmsship archive ({error})") from None

    with archive:
        objects = _read_json(archive, OBJECTS_FILE)
        ship = _read_json(archive, SHIP_FILE)
        customisation = _read_json(archive, CUSTOMISATION_FILE)

    validate_parts(objects, OBJECTS_FILE)
    if not isinstance(ship, dict):
        raise NmsShipError(f"{SHIP_FILE} must be an object")
    if not isinstance(customisation, dict):
        raise NmsShipError(f"{CUSTOMISATION_FILE} must be an object")
    return objects, ship, customisation


def read_parts_text(text):
    """(parts, BaseVersion) of a .json/.txt ship, a bare array or {"Objects": [...]},
    validated. Raises NmsShipError."""
    if not text or not text.strip():
        raise NmsShipError("it is empty")
    try:
        data = json.loads(text)
    except ValueError as error:
        raise NmsShipError(f"it is not valid JSON ({error})") from None

    base_version = DEFAULT_BASE_VERSION
    if isinstance(data, dict):
        if "Objects" not in data:
            raise NmsShipError('it must be an array of parts or have an "Objects" array')
        version = data.get("BaseVersion", DEFAULT_BASE_VERSION)
        if isinstance(version, bool) or not isinstance(version, int):
            raise NmsShipError('"BaseVersion" must be a whole number')
        base_version = version
        data = data["Objects"]
    validate_parts(data, "the file")
    return data, base_version


def read_any(path):
    """(parts, ship record, customisation, BaseVersion) of any ship file, told apart by
    its contents: a zip is a .nmsship, else .json/.txt. Raises NmsShipError."""
    if zipfile.is_zipfile(path):
        return read(path) + (DEFAULT_BASE_VERSION,)

    try:
        with open(path, "r", encoding="utf-8-sig") as ship_file:
            text = ship_file.read()
    except (OSError, UnicodeDecodeError) as error:
        raise NmsShipError(f"it could not be read ({error})") from None
    parts, base_version = read_parts_text(text)
    return parts, None, None, base_version


def write_json(path, objects):
    """Write parts as a .json ship, {"Objects": [...]}."""
    temp_path = path + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as ship_file:
            json.dump({"Objects": objects}, ship_file, indent=2, ensure_ascii=False)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def new_seed():
    """A fresh ship seed, in the game's [valid, "0x..."] form."""
    return [True, "0x%016X" % random.getrandbits(64)]


def load_template():
    """(ship record, customisation) from the template, for a ship that has none,
    given a fresh seed each time."""
    with open(TEMPLATE_JSON, "r", encoding="utf-8") as template_file:
        template = json.load(template_file)
    ship = template["so"]
    ship["Resource"]["Seed"] = new_seed()
    return ship, template["ccd"]


def _encode(data, indent):
    # the files the game tools write: BOM, CRLF line ends, 2 space indent
    # for the big two and compact for ccd.json
    if indent:
        text = json.dumps(data, indent=2, ensure_ascii=False).replace("\n", "\r\n")
    else:
        text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8-sig")


def write(path, objects, ship, customisation):
    """Write a .nmsship file, written beside `path` first and moved into place
    so a failure never leaves a broken file."""
    temp_path = path + ".tmp"
    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(OBJECTS_FILE, _encode(objects, indent=True))
            archive.writestr(SHIP_FILE, _encode(ship, indent=True))
            archive.writestr(CUSTOMISATION_FILE, _encode(customisation, indent=False))
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
