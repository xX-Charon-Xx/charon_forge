"""Where the colour data is on disk."""

import os

ADDON_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
RESOURCES_PATH = os.path.join(ADDON_PATH, "resources")

# The high res library's textures - what its assets' images point at, and
# what packing.py packs into a saved .blend.
TEXTURES_PATH = os.path.join(ADDON_PATH, "asset_browser", "textures")

# The game's palette table, one row per (colour, finish) pair.
COLOURS_CSV = os.path.join(RESOURCES_PATH, "DT_Palettes.csv")

# Parts that draw semi transparent, their flat material gets "_transparent".
GHOSTED_JSON = os.path.join(RESOURCES_PATH, "ghosted.json")

# All 151 palettes with all four slots, for the high res library.
PALETTE_JSON = os.path.join(RESOURCES_PATH, "colour_palette_by_index.json")

# The game's palettes, finishes and per part colour groups, written by
# the extraction pipeline alongside the library. See game_data.py.
COLOURS_JSON = os.path.join(RESOURCES_PATH, "colours.json")
