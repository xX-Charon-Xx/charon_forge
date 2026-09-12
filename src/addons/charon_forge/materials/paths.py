"""Where the colour data is on disk."""

import os

ADDON_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
RESOURCES_PATH = os.path.join(ADDON_PATH, "nms", "resources")

# The game's palette table, one row per (colour, finish) pair.
COLOURS_CSV = os.path.join(RESOURCES_PATH, "DT_Palettes.csv")

# Parts that draw semi transparent, their flat material gets "_transparent".
GHOSTED_JSON = os.path.join(RESOURCES_PATH, "ghosted.json")

# All 151 palettes with all four slots, for the high res library.
PALETTE_JSON = os.path.join(RESOURCES_PATH, "colour_palette_by_index.json")

# What each finish does to a high res part's surface. Ours rather than the
# game's, so it lives with Charon Forge's own resources.
FINISHES_JSON = os.path.join(ADDON_PATH, "resources", "finishes.json")
