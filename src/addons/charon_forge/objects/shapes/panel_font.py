"""Fonts drawn in panels - The Forge's "Forge Text".

A letter is a handful of strokes, each a straight line. Every stroke is laid
with STORAGEPANELs end to end along it, each scaled so its long side is the
stroke's length split between them - so a stroke as long as a panel at the
font's weight is exactly one panel, and a longer one costs more. The panel
only scales evenly, which ties a stroke's thickness to its length: a font is
drawn around that, out of strokes about one panel long.

Everything here is in font units, y upwards from the baseline; the weight of
a stroke is 1 unit. objects/shapes/text.py lays the panels out.
"""

import math

# the panel's long side over its short side, at the font's weight - a stroke
# this long is one panel exactly 1 unit thick
PANEL = 2.4

# a stroke is split into more panels only once one would be thicker than this
MAX_WEIGHT = 1.45

# rounded up or down by less than this, a count is taken as exact
_FIT = 1e-4


class Font:
    """A font: its glyphs, each (advance width, strokes), a stroke being
    (x0, y0, x1, y1, thickest) - the line down the middle of it, end to end,
    and the thickest a panel laying it may be before it takes two."""

    def __init__(self, name, label, description, height, spacing, space, glyphs):
        self.name = name
        self.label = label
        self.description = description
        self.height = height
        self.spacing = spacing
        self.space = space
        self.glyphs = glyphs

    def glyph(self, character):
        """The glyph drawing a character, or None when the font has none -
        lower case is drawn in capitals."""
        if character == " ":
            return (self.space, ())
        return self.glyphs.get(character) or self.glyphs.get(character.upper())

    def missing(self, text):
        """The characters of the text the font can't draw, each once."""
        return "".join(sorted({character for character in text if self.glyph(character) is None}))


# The fonts ---
# The block families are drawn on one grid of bars and stems, the bars a
# panel long at weight 1 between the stems, which sets how big a letter is. A
# stem's weight is set by how it is laid, which is what tells them apart:
#   Poster    a whole stem one panel, top to bottom - which makes it more
#             than twice as thick, and the fewest parts of any
#   Segments  each half of a stem one panel, meeting the bars in the middle
#             of each bar row - the letters' outer corners are notched
#   Wide      Segments with bars two panels long, for letters half as wide
#             again - a panel more for each bar
# Segments and Wide come in bold and italic too, Poster in italic:
#   bold      each half stem two panels side by side, twice as thick, and
#             the diagonals let grow thicker to match - a panel more per half
#             stem, the diagonals often a panel fewer
#   italic    every stroke sheared over to the right, at no cost
# Diagonals run corner to corner where a letter needs one and take whatever
# thickness their length gives them.
#
# The organic families are drawn freehand instead, each letter a few
# polylines rounding its corners off with diagonals (see _organic_glyphs).
# Their strokes are as thick as they are long, so the short turns come out
# thinner than the long sides, the way a broad pen draws:
#   Rounded   upright, and in italic too
#   Script    the same letters leaning well over and set closer together
FAMILIES = (
    # name, label, description, icon, number - the number is what a saved
    # text keeps, so a family keeps its own however the list is ordered
    ("POSTER", "Poster", "Every stem one thick panel top to bottom - heavy letters, the fewest parts",
     "NONE", 3),
    ("SEGMENTS", "Segments", "Every stroke one panel, corners notched", "NONE", 0),
    ("WIDE", "Wide", "Segments with bars twice as long - wider letters, a panel more per bar",
     "NONE", 2),
    ("ROUNDED", "Rounded", "Letters drawn freehand with rounded corners - organic, a few more parts",
     "NONE", 4),
    ("SCRIPT", "Script", "Rounded letters leaning over like handwriting, set close together",
     "NONE", 5),
)

# what a text is drawn in when its family is gone
DEFAULT_FAMILY = "POSTER"

# the families already as heavy as they go, or drawn freehand
NO_BOLD = {"POSTER", "ROUNDED", "SCRIPT"}

# the families leaning over already
NO_ITALIC = {"SCRIPT"}

ORGANIC = {"ROUNDED", "SCRIPT"}

# how far an italic leans: across for every unit up
ITALIC_SLANT = 0.2

# and Script
SCRIPT_SLANT = 0.35

# the thickest a bold diagonal may be before it takes another panel
BOLD_DIAGONAL_WEIGHT = 2.1

# the thickest any Poster stroke may be - a whole stem is one panel
POSTER_WEIGHT = 2.6

# the thickest an organic stroke may be - a whole stem is two panels
ORGANIC_WEIGHT = 1.6


def has_bold(family):
    return family not in NO_BOLD


def has_italic(family):
    return family not in NO_ITALIC


class _Grid:
    """Where a family's bars and stems go."""

    def __init__(self, family, bold):
        self.family = family
        self.poster = family == "POSTER"
        self.bold = bold and has_bold(family)
        self.bar = 2 * PANEL if family == "WIDE" else PANEL
        self.H = 5.8                                     # how tall a capital is
        self.B, self.M, self.T = 0.5, 2.9, 5.3           # the bars' middles
        # half a stem's thickness
        if self.poster:
            self.half = self.H / PANEL / 2
        else:
            self.half = 1.0 if self.bold else 0.5
        self.L = self.half                               # the left stem's middle
        self.I0 = 2 * self.half                          # the bars run from here
        self.I1 = self.I0 + self.bar                     # to here
        self.R = self.I1 + self.half                     # the right stem's middle
        self.W = self.R + self.half                      # a full letter's width
        self.C = self.W / 2                              # the middle of a letter
        # each half stem, bottom to top
        if self.poster:
            # to the far side of the middle bar, flush with the inside of the
            # letter - a whole stem is one panel, top to bottom
            self.lower, self.upper = (0.0, 3.4), (2.4, 5.8)
        else:
            self.lower, self.upper = (self.B, self.M), (self.M, self.T)

        # the thickest a straight stroke and a diagonal may be
        if self.poster:
            self.straight_weight = self.diagonal_weight = POSTER_WEIGHT
        else:
            self.straight_weight = MAX_WEIGHT
            self.diagonal_weight = BOLD_DIAGONAL_WEIGHT if self.bold else MAX_WEIGHT

    def stem(self, x, y0, y1):
        """A stem centred on x: two panels side by side in bold."""
        if self.bold:
            return ((x - 0.5, y0, x - 0.5, y1), (x + 0.5, y0, x + 0.5, y1))
        return ((x, y0, x, y1),)


def _glyphs(g):
    """Every glyph of a family, drawn on its grid."""
    if g.poster:
        # a half stem is as thick as its length makes it, so it is set in
        # against the bars rather than centred where a whole one would be
        side = (g.lower[1] - g.lower[0]) / PANEL / 2
        segments = {
            "b": ((g.I1 + side, g.upper[0], g.I1 + side, g.upper[1]),),
            "c": ((g.I1 + side, g.lower[0], g.I1 + side, g.lower[1]),),
            "e": ((g.I0 - side, g.lower[0], g.I0 - side, g.lower[1]),),
            "f": ((g.I0 - side, g.upper[0], g.I0 - side, g.upper[1]),),
        }
    else:
        segments = {
            "b": g.stem(g.R, *g.upper),     # upper right
            "c": g.stem(g.R, *g.lower),     # lower right
            "e": g.stem(g.L, *g.lower),     # lower left
            "f": g.stem(g.L, *g.upper),     # upper left
        }
    segments.update({
        "a": ((g.I0, g.T, g.I1, g.T),),     # top bar
        "d": ((g.I0, g.B, g.I1, g.B),),     # bottom bar
        "g": ((g.I0, g.M, g.I1, g.M),),     # middle bar
        # whole stems, where a letter has both halves
        "E": g.stem(g.L, 0.0, g.H) if g.poster else segments["e"] + segments["f"],
        "B": g.stem(g.R, 0.0, g.H) if g.poster else segments["b"] + segments["c"],
    })

    def seg(names, *extra, width=g.W):
        # both halves of a stem are laid as one
        if "e" in names and "f" in names:
            names = names.replace("e", "").replace("f", "") + "E"
        if "b" in names and "c" in names:
            names = names.replace("b", "").replace("c", "") + "B"
        return (width, sum((segments[name] for name in names), ()) + extra)

    # a D's bars stop a panel along, however wide the family is, and its
    # right side slants in to a point off their ends
    d_end = g.L + g.bar
    glyphs = {
        "A": seg("abcefg"),
        # the upper bowl narrower, so it isn't an 8
        "B": (g.W, segments["a"] + segments["d"] + segments["g"] + segments["E"]
              + segments["c"] + g.stem(g.R - 0.5, *g.upper)),
        "C": seg("adef"),
        # the bars over its left corners and its right side slanted in to a
        # point, so it isn't an O
        "D": seg("ef", (g.L, g.T, d_end, g.T), (g.L, g.B, d_end, g.B),
                 (d_end - 0.3, g.T + 0.2, d_end + 1.0, g.M),
                 (d_end - 0.3, g.B - 0.2, d_end + 1.0, g.M), width=d_end + 1.5),
        "E": seg("adefg"),
        "F": seg("aefg"),
        "G": seg("acdef"),
        "H": seg("bcefg"),
        "I": seg("ef", width=2 * g.half),
        "J": seg("bcde"),
        "K": seg("ef", (g.I0 + 0.2, g.M + 0.1, g.R - 0.3, g.T),
                 (g.I0 + 0.2, g.M - 0.1, g.R - 0.3, g.B)),
        "L": seg("def"),
        "M": seg("bcef", (g.I0, g.T, g.C, g.M + 0.1), (g.I1, g.T, g.C, g.M + 0.1)),
        "N": seg("bcef", (g.I0, g.T, g.I1, g.B)),
        "O": seg("abcdef"),
        "P": seg("abefg"),
        "Q": seg("abcdef", (g.C + 0.4, 1.6, g.R + 0.3, 0.0)),
        "R": seg("abefg", (g.I0 + 0.6, g.M - 0.3, g.R, 0.3)),
        "S": seg("acdfg"),
        "T": (g.bar, ((0.0, g.T, g.bar, g.T),) + g.stem(g.bar / 2, 0.0, 4.8)),
        "U": seg("bcdef"),
        "V": (g.W, ((g.L, g.T, g.C, 0.2), (g.R, g.T, g.C, 0.2))),
        "W": seg("bcef", (g.I0, g.B, g.C, g.M - 0.1), (g.I1, g.B, g.C, g.M - 0.1)),
        "X": (g.W, ((g.L, g.T, g.R, g.B), (g.R, g.T, g.L, g.B))),
        "Y": (g.W, ((g.L, g.T, g.C, 2.6), (g.R, g.T, g.C, 2.6)) + g.stem(g.C, 0.2, 2.6)),
        "Z": seg("ad", (g.I1, g.T - 0.5, g.I0, g.B + 0.5)),

        "0": seg("abcdef", (g.I1, g.T - 0.5, g.I0, g.B + 0.5)),
        "1": (2.4 + g.half, (g.stem(1.4 + g.half, 0.0, g.H) if g.poster else
                             g.stem(1.4 + g.half, *g.lower) + g.stem(1.4 + g.half, *g.upper))
              + ((0.2, 4.0, 0.9 + g.half, g.T),)),
        "2": seg("abdeg"),
        "3": seg("abcdg"),
        "4": seg("bcfg"),
        "5": seg("acdfg"),
        "6": seg("acdefg"),
        "7": seg("abc"),
        "8": seg("abcdefg"),
        "9": seg("abcdfg"),

        ".": (0.8, ((0.4, 0.0, 0.4, 1.2),)),
        ",": (1.0, ((0.7, 1.0, 0.2, -0.5),)),
        ":": (0.8, ((0.4, 0.4, 0.4, 1.6), (0.4, 3.4, 0.4, 4.6))),
        ";": (1.0, ((0.5, 3.4, 0.5, 4.6), (0.7, 1.0, 0.2, -0.5))),
        "!": (2 * g.half, g.stem(g.half, 2.6, 5.3) + ((g.half, 0.0, g.half, 1.2),)),
        "?": seg("abg", (g.C, 0.0, g.C, 1.2)),
        "'": (1.0, ((0.5, 4.0, 0.5, 5.8),)),
        '"': (2.2, ((0.5, 4.0, 0.5, 5.8), (1.7, 4.0, 1.7, 5.8))),
        "-": (2.4, ((0.0, g.M, 2.4, g.M),)),
        "+": (2.4, ((0.0, g.M, 2.4, g.M), (1.2, 1.7, 1.2, 4.1))),
        "=": (2.4, ((0.0, 2.1, 2.4, 2.1), (0.0, 3.7, 2.4, 3.7))),
        "_": (2.4, ((0.0, g.B, 2.4, g.B),)),
        "/": (2.4, ((0.0, g.B, 2.4, g.T),)),
        "\\": (2.4, ((0.0, g.T, 2.4, g.B),)),
        "(": (1.8, ((0.5, 1.7, 0.5, 4.1), (0.6, 4.0, 1.7, 5.6), (0.6, 1.8, 1.7, 0.2))),
    }
    glyphs[")"] = (1.8, tuple((1.8 - x0, y0, 1.8 - x1, y1) for x0, y0, x1, y1 in glyphs["("][1]))
    return _weighed(glyphs, g.straight_weight, g.diagonal_weight)


def _weighed(glyphs, straight_weight, diagonal_weight):
    """The glyphs with how thick each stroke may grow, worked out while it is
    still upright - an italic leans every stroke over."""
    def weighed(stroke):
        x0, y0, x1, y1 = stroke
        straight = abs(x1 - x0) < 1e-6 or abs(y1 - y0) < 1e-6
        return stroke + (straight_weight if straight else diagonal_weight,)

    return {
        character: (width, tuple(weighed(stroke) for stroke in strokes))
        for character, (width, strokes) in glyphs.items()
    }


# Organic ---
# how tall a capital is, and the lines down the middle of its strokes
_O_HEIGHT = 6.0
_ob, _om, _ot = 0.5, 3.0, 5.5      # bottom, middle and top
_ohi, _olo = 4.0, 2.0              # where a round side turns in, top and bottom


def _lines(*points):
    """The strokes along a polyline."""
    return tuple(points[index] + points[index + 1] for index in range(len(points) - 1))


def _organic_glyphs():
    """Every glyph of the organic families: (width, strokes) each, the
    strokes read off polylines. A round letter is a hexagon - its sides
    turning in to a point at the top and bottom - so no stroke is short
    enough to come out thin."""
    l, c, r = 0.5, 2.5, 4.5
    b, m, t, hi, lo = _ob, _om, _ot, _ohi, _olo
    W = 5.0

    def glyph(width, *polylines):
        return (width, sum((_lines(*polyline) for polyline in polylines), ()))

    stem = ((l, b), (l, t))
    bowl = ((l, hi), (c, t), (r, hi), (r, lo), (c, b), (l, lo), (l, hi))
    glyphs = {
        "A": glyph(W, ((l, b), (l, hi), (c, t), (r, hi), (r, b)), ((l, m), (r, m))),
        "B": glyph(4.6, stem, ((l, t), (2.6, t), (3.8, 4.25), (2.6, m), (l, m)),
                   ((l, m), (2.8, m), (4.1, 1.75), (2.8, b), (l, b))),
        "C": glyph(W, ((r, hi), (c, t), (l, hi), (l, lo), (c, b), (r, lo))),
        "D": glyph(W, stem, ((l, t), (c, t), (r, hi), (r, lo), (c, b), (l, b))),
        # a backwards 3, the way it is written
        "E": glyph(4.6, ((4.0, 4.6), (2.3, t), (0.7, 4.4), (1.8, m), (0.6, 1.6),
                         (2.3, b), (4.1, 1.3))),
        "F": glyph(3.9, stem, ((l, t), (3.4, t)), ((l, m), (2.8, m))),
        "G": glyph(W, ((r, hi), (c, t), (l, hi), (l, lo), (c, b), (r, lo), (r, 3.2), (2.6, 3.2))),
        "H": glyph(W, stem, ((r, b), (r, t)), ((l, m), (r, m))),
        "I": glyph(1.0, stem),
        "J": glyph(4.0, ((3.5, t), (3.5, lo), (2.0, b), (l, lo))),
        "K": glyph(4.6, stem, ((4.0, t), (1.0, m), (4.2, b))),
        "L": glyph(3.9, ((l, t), (l, b), (3.4, b))),
        "M": glyph(W, ((l, b), (l, t), (c, m), (r, t), (r, b))),
        "N": glyph(W, ((l, b), (l, t), (r, b), (r, t))),
        "O": glyph(W, bowl),
        "P": glyph(4.6, stem, ((l, t), (2.6, t), (4.1, 4.15), (2.6, 2.8), (l, 2.8))),
        "Q": glyph(W, bowl, ((3.0, 1.6), (4.9, -0.2))),
        "R": glyph(4.8, stem, ((l, t), (2.6, t), (4.1, 4.15), (2.6, 2.8), (l, 2.8)),
                   ((2.4, 2.8), (4.3, b))),
        "S": glyph(W, ((4.3, 4.6), (c, t), (0.7, 4.5), (4.3, 1.5), (c, b), (0.7, 1.4))),
        "T": glyph(3.0, ((0.0, t), (3.0, t)), ((1.5, t), (1.5, b))),
        "U": glyph(W, ((l, t), (l, lo), (c, b), (r, lo), (r, t))),
        "V": glyph(W, ((l, t), (c, b), (r, t))),
        "W": glyph(W, ((l, t), (1.5, b), (c, 3.5), (3.5, b), (r, t))),
        "X": glyph(W, ((l, t), (r, b)), ((r, t), (l, b))),
        "Y": glyph(W, ((l, t), (c, m), (r, t)), ((c, m), (c, b))),
        "Z": glyph(3.6, ((l, t), (3.1, t), (l, b), (3.1, b))),

        "0": glyph(W, bowl),
        "1": glyph(3.0, ((1.0, 4.3), (2.5, t), (2.5, b))),
        "2": glyph(4.4, ((0.6, 4.4), (2.2, t), (3.8, 4.4), (l, b), (3.9, b))),
        "3": glyph(4.4, ((0.6, 4.8), (2.1, t), (3.7, 4.5), (2.1, m), (3.9, 1.6), (2.1, b),
                         (l, 1.2))),
        "4": glyph(4.4, ((3.0, b), (3.0, t), (l, lo), (3.9, lo))),
        "5": glyph(4.4, ((3.8, t), (0.8, t), (0.6, 3.3), (2.4, 3.6), (3.9, 2.1), (2.4, b),
                         (l, 1.2))),
        "6": glyph(4.4, ((3.5, t), (1.2, 3.8), (l, lo), (2.2, b), (3.9, 1.8), (2.3, 3.4),
                         (0.8, 2.6))),
        "7": glyph(4.4, ((l, t), (3.9, t), (1.6, b))),
        "8": glyph(4.4, ((2.2, m), (0.8, 4.3), (2.2, t), (3.6, 4.3), (2.2, m), (0.6, 1.75),
                         (2.2, b), (3.8, 1.75), (2.2, m))),
        "9": glyph(4.4, ((0.9, b), (3.2, 2.2), (3.9, lo + 1.7), (2.2, t), (0.5, 4.2),
                         (2.1, 2.6), (3.6, 3.4))),

        ".": glyph(0.8, ((0.4, 0.0), (0.4, 1.2))),
        ",": glyph(1.0, ((0.7, 1.0), (0.2, -0.5))),
        ":": glyph(0.8, ((0.4, 0.4), (0.4, 1.6)), ((0.4, 3.4), (0.4, 4.6))),
        ";": glyph(1.0, ((0.5, 3.4), (0.5, 4.6)), ((0.7, 1.0), (0.2, -0.5))),
        "!": glyph(1.0, ((0.5, 2.4), (0.5, t)), ((0.5, 0.0), (0.5, 1.2))),
        "?": glyph(4.4, ((0.6, 4.4), (2.2, t), (3.8, 4.4), (2.2, 2.6), (2.2, 1.6)),
                   ((2.2, 0.0), (2.2, 1.0))),
        "'": glyph(1.0, ((0.5, 4.2), (0.5, 6.0))),
        '"': glyph(2.2, ((0.5, 4.2), (0.5, 6.0)), ((1.7, 4.2), (1.7, 6.0))),
        "-": glyph(2.4, ((0.0, m), (2.4, m))),
        "+": glyph(2.4, ((0.0, m), (2.4, m)), ((1.2, 1.8), (1.2, 4.2))),
        "=": glyph(2.4, ((0.0, 2.2), (2.4, 2.2)), ((0.0, 3.8), (2.4, 3.8))),
        "_": glyph(2.4, ((0.0, b), (2.4, b))),
        "/": glyph(2.4, ((0.0, b), (2.4, t))),
        "\\": glyph(2.4, ((0.0, t), (2.4, b))),
        "(": glyph(1.8, ((1.7, 6.0), (0.5, 4.2), (0.5, 1.8), (1.7, 0.0))),
        ")": glyph(1.8, ((0.1, 6.0), (1.3, 4.2), (1.3, 1.8), (0.1, 0.0))),
    }
    return _weighed(glyphs, ORGANIC_WEIGHT, ORGANIC_WEIGHT)


def _slanted(glyphs, slant, middle):
    """The glyphs sheared over by `slant` across for every unit up, about
    the height `middle` - so the letters stay where they were, on average."""
    return {
        character: (width, tuple(
            (x0 + slant * (y0 - middle), y0, x1 + slant * (y1 - middle), y1, weight)
            for x0, y0, x1, y1, weight in strokes
        ))
        for character, (width, strokes) in glyphs.items()
    }


def _fitted(glyphs):
    """The glyphs each as wide as what it draws, from its left edge - so
    every letter stands the font's spacing off the next, whether or not it
    has a stem on each side. Worked out while they are upright, so an
    italic keeps its letters where they stand."""
    fitted = {}
    for character, (width, strokes) in glyphs.items():
        edges = []
        for stroke in strokes:
            for centre_x, _centre_y, angle, long_side in plan_stroke(stroke):
                # a panel's corners, across the line
                along = abs(math.cos(angle)) * long_side / 2
                across = abs(math.sin(angle)) * long_side / PANEL / 2
                edges += (centre_x - along - across, centre_x + along + across)
        if not edges:
            fitted[character] = (width, strokes)
            continue
        left = min(edges)
        fitted[character] = (max(edges) - left, tuple(
            (x0 - left, y0, x1 - left, y1, weight) for x0, y0, x1, y1, weight in strokes
        ))
    return fitted


def _make_font(family, bold, italic):
    name, label, description = next(entry for entry in FAMILIES if entry[0] == family)[:3]
    spacing = 1.0
    if family in ORGANIC:
        height = _O_HEIGHT
        glyphs = _fitted(_organic_glyphs())
        if family == "SCRIPT":
            glyphs = _slanted(glyphs, SCRIPT_SLANT, height / 2)
            spacing = 0.4
    else:
        grid = _Grid(family, bold)
        height = grid.H
        glyphs = _fitted(_glyphs(grid))
    if italic:
        glyphs = _slanted(glyphs, ITALIC_SLANT, height / 2)
    style = " ".join(word for word, on in (("Bold", bold), ("Italic", italic)) if on)
    return Font(
        name, f"{label} {style}".strip(), description,
        height=height, spacing=spacing, space=2.4, glyphs=glyphs,
    )


_fonts = {}


def get_font(family, bold=False, italic=False):
    """A family's font, in bold or italic or both - None for no such family.
    A style the family has none of is ignored."""
    if not any(entry[0] == family for entry in FAMILIES):
        return None
    key = (family, bool(bold) and has_bold(family), bool(italic) and has_italic(family))
    if key not in _fonts:
        _fonts[key] = _make_font(*key)
    return _fonts[key]



# Planning ---
def plan_stroke(stroke, ratio=PANEL):
    """The panels laying one stroke: (centre x, centre y, angle, long side)
    each, the angle that of the stroke from the x axis."""
    x0, y0, x1, y1, weight = stroke
    length = math.hypot(x1 - x0, y1 - y0)
    count = max(1, math.ceil(length / (ratio * weight) - _FIT))
    angle = math.atan2(y1 - y0, x1 - x0)
    return [
        (x0 + (x1 - x0) * (index + 0.5) / count,
         y0 + (y1 - y0) * (index + 0.5) / count,
         angle, length / count)
        for index in range(count)
    ]


def plan(text, font, ratio=PANEL, spacing=0.0):
    """Every panel of a line of text, laid left to right from the origin.

    Args:
        spacing (float): Room added between the letters, in font units -
            negative closes them up.

    Returns:
        tuple: (the panels - (centre x, centre y, angle, long side) each, in
        font units - and the width of the line).

    Raises:
        ValueError: When the font can't draw some of the text.
    """
    missing = font.missing(text)
    if missing:
        raise ValueError(f"the font has no {' '.join(missing)}")

    panels = []
    x = 0.0
    for index, character in enumerate(text):
        width, strokes = font.glyph(character)
        for stroke in strokes:
            for centre_x, centre_y, angle, long_side in plan_stroke(stroke, ratio):
                panels.append((x + centre_x, centre_y, angle, long_side))
        x += width
        if index < len(text) - 1:
            x += font.spacing + spacing
    return panels, x


# every family, plain
FONTS = {entry[0]: get_font(entry[0]) for entry in FAMILIES}
