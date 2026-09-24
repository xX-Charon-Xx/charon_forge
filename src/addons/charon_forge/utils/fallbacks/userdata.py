"""Reading and writing the colour and material in a UserData value - the base
builder addon's utils/userdata.py.

Only the colour (low 24 bits) and material (bits 24-31) regions are touched;
every other bit is kept. Bits 8, 16 and 17 sit inside the colour range but
are not colour, so they are kept too.
"""

COLOUR_BITS_FULL = 0xFFFFFF
RESERVED_BITS = (1 << 8) | (1 << 16) | (1 << 17)
COLOUR_MASK = COLOUR_BITS_FULL & ~RESERVED_BITS

MATERIAL_SHIFT = 24
MATERIAL_MASK = 0xFF << MATERIAL_SHIFT


def get_colour(value):
    return value & COLOUR_MASK


def set_colour(value, colour_index):
    return (value & ~COLOUR_MASK) | (colour_index & COLOUR_MASK)


def get_material(value):
    return (value & MATERIAL_MASK) >> MATERIAL_SHIFT


def set_material(value, material_index):
    return (value & ~MATERIAL_MASK) | ((material_index << MATERIAL_SHIFT) & MATERIAL_MASK)


def update_colour_material(base_value, *, colour_index=None, material_index=None):
    """`base_value` with the colour and/or material replaced (None = unchanged)."""
    value = base_value
    if colour_index is not None:
        value = set_colour(value, colour_index)
    if material_index is not None:
        value = set_material(value, material_index)
    return value
