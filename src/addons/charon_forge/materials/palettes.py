"""The game's colour tables (DT_Palettes.csv, colour_palette_by_index.json).
UserData: colour index = UserData & 0xFFFFFF, finish index = (UserData >> 24) & 0xFF."""

import csv
import json
import re

from ..utils.base_builder_utils import userdata
from . import paths


# Flat palette table (CSV) ---
def get_palette_from_row(row):
    return row[2]


def get_palette_index_from_row(row):
    return row[4]


def _read_csv_rows():
    with open(paths.COLOURS_CSV, "r") as csv_file:
        csv_reader = csv.reader((x.replace("\0", "") for x in csv_file), delimiter=",")
        for idx, row in enumerate(csv_reader):
            if idx == 0:
                continue
            yield row


def get_all_palettes():
    palettes = {}
    for row in _read_csv_rows():
        palette_name = get_palette_from_row(row)
        if palette_name not in palettes:
            palettes[palette_name] = get_palette_index_from_row(row)
    return palettes


BAKED_PALETTES = get_all_palettes()
BAKED_PALETTES_UI = [
    (f"{value}_{key}", key, key) for key, value in BAKED_PALETTES.items()
]

BAKED_INDEX_COLOURS = {}


def get_all_colours():
    rows = []
    for row in _read_csv_rows():
        rows.append(row)

        colour_id = row[3]
        primary_colour = row[6]
        if isinstance(primary_colour, str):
            primary_colour = [
                float(v) for v in re.findall(r"[RGB]=([0-9.]+)", primary_colour)
            ]
        BAKED_INDEX_COLOURS[int(colour_id)] = primary_colour
    return rows


BAKED_COLOURS = get_all_colours()


def get_nice_name_from_indicies(colour_index, material_index):
    """"<finish>: <colour>" for a colour and finish index, or ""."""
    for row in BAKED_COLOURS:
        if int(colour_index) == int(row[3]) and int(material_index) == int(row[4]):
            return f"{row[2]}: {row[5]}"
    return ""


def get_colours_from_palette(palette):
    palette_string = palette.split("_")[1]
    return [row for row in BAKED_COLOURS if palette_string == get_palette_from_row(row)]


def get_colour_from_palette_data(colour_index, material_index):
    """The flat colour for a colour index."""
    return BAKED_INDEX_COLOURS.get(colour_index, [0.8, 0.8, 0.8, 1.0])


def darken_color(color, factor=0.6):
    """Return a darker version of an RGB color."""
    return [c * factor for c in color]


# Four slot palette table (JSON) ---
# loaded on first use, not at import
_palette_by_index = None
_colour_labels = None
_finish_labels = None


def _load_palettes():
    """Load and cache the palette table and labels; labels come from the CSV first,
    as the finish index is only unique together with the colour index."""
    global _palette_by_index, _colour_labels, _finish_labels
    if _palette_by_index is not None:
        return _palette_by_index, _colour_labels, _finish_labels

    with open(paths.PALETTE_JSON, "r", encoding="utf-8") as palette_file:
        raw = json.load(palette_file)
    _palette_by_index = {int(key): value for key, value in raw.items()}

    _colour_labels = {}
    _finish_labels = {}
    for row in BAKED_COLOURS:
        try:
            colour_index = int(row[3])
            _colour_labels[colour_index] = row[5]
            _finish_labels[(colour_index, int(row[4]))] = row[2]
        except (IndexError, ValueError):
            continue

    return _palette_by_index, _colour_labels, _finish_labels


def decode_user_data(user_data_value):
    """(colour index, finish index) for a UserData value, or None if not a number."""
    try:
        value = int(user_data_value)
    except (TypeError, ValueError):
        return None
    return userdata.get_colour(value), userdata.get_material(value)


def get_palette(user_data_value):
    """The palette entry {id, name_en, p, s, t, q} for a UserData value, or None."""
    indices = decode_user_data(user_data_value)
    if indices is None:
        return None
    return _load_palettes()[0].get(indices[0])


def get_nice_names(user_data_value):
    """(colour name, finish name) for a UserData value; either can be None."""
    indices = decode_user_data(user_data_value)
    if indices is None:
        return None, None

    palettes, colour_labels, finish_labels = _load_palettes()
    colour_name = colour_labels.get(indices[0])
    if colour_name is None:
        palette = palettes.get(indices[0])
        colour_name = palette.get("name_en") if palette else None

    return colour_name, finish_labels.get(indices)
