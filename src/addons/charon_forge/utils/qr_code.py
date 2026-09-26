"""A QR code encoder - text in, a grid of dark and light modules out.

Blender's Python has no QR library, so this is a small one of our own, byte
mode only (any text, as UTF-8), following ISO/IEC 18004: the smallest version
that fits, Reed-Solomon error correction, and the mask with the lowest
penalty. The Forge builds the grid out of parts - see utils/qr_forge.py.

    modules = encode("https://example.com", "M")   # list of rows of bools
"""

ERROR_LEVELS = ("L", "M", "Q", "H")

# the two format bits each level is written as
_FORMAT_BITS = {"L": 1, "M": 0, "Q": 3, "H": 2}

# error correction codewords per block, by level then version (index 0 unused)
_ECC_CODEWORDS_PER_BLOCK = {
    "L": (-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    "M": (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),
    "Q": (-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    "H": (-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
}

# error correction blocks, by level then version (index 0 unused)
_ECC_BLOCKS = {
    "L": (-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25),
    "M": (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49),
    "Q": (-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68),
    "H": (-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81),
}

MIN_VERSION = 1
MAX_VERSION = 40


class QRCodeError(ValueError):
    pass


# Sizes ---
def _raw_data_modules(version):
    """Modules left for data and error correction once the function
    patterns are drawn - codewords times eight, plus remainder bits."""
    result = (16 * version + 128) * version + 64
    if version >= 2:
        alignments = version // 7 + 2
        result -= (25 * alignments - 10) * alignments - 55
        if version >= 7:
            result -= 36
    return result


def _data_codewords(version, level):
    return (_raw_data_modules(version) // 8
            - _ECC_CODEWORDS_PER_BLOCK[level][version] * _ECC_BLOCKS[level][version])


def _alignment_positions(version):
    if version == 1:
        return []
    count = version // 7 + 2
    step = 26 if version == 32 else (version * 4 + count * 2 + 1) // (count * 2 - 2) * 2
    positions = [6]
    size = version * 4 + 17
    for index in range(count - 1):
        positions.insert(1, size - 7 - index * step)
    return positions


# Reed-Solomon ---
def _gf_multiply(x, y):
    """Multiply in GF(2^8) modulo x^8 + x^4 + x^3 + x^2 + 1."""
    z = 0
    for bit in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> bit) & 1) * x
    return z


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for index in range(degree):
            result[index] = _gf_multiply(result[index], root)
            if index + 1 < degree:
                result[index] ^= result[index + 1]
        root = _gf_multiply(root, 0x02)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for byte in data:
        factor = byte ^ result.pop(0)
        result.append(0)
        for index, coefficient in enumerate(divisor):
            result[index] ^= _gf_multiply(coefficient, factor)
    return result


def _add_error_correction(data, version, level):
    """Split the data into blocks, add each block's error correction, and
    interleave them the way the code is read."""
    block_count = _ECC_BLOCKS[level][version]
    ecc_length = _ECC_CODEWORDS_PER_BLOCK[level][version]
    raw_codewords = _raw_data_modules(version) // 8
    short_blocks = block_count - raw_codewords % block_count
    short_length = raw_codewords // block_count

    divisor = _rs_divisor(ecc_length)
    blocks = []
    offset = 0
    for index in range(block_count):
        length = short_length - ecc_length + (0 if index < short_blocks else 1)
        block = data[offset:offset + length]
        offset += length
        ecc = _rs_remainder(block, divisor)
        if index < short_blocks:
            block = block + [0]      # padded so every block is the same length
        blocks.append(block + ecc)

    result = []
    for position in range(len(blocks[0])):
        for index, block in enumerate(blocks):
            # the short blocks' padding byte isn't part of the code
            if position != short_length - ecc_length or index >= short_blocks:
                result.append(block[position])
    return result


# Data ---
def _encode_data(text, version, level):
    data = text.encode("utf-8")
    bits = []

    def append(value, length):
        bits.extend((value >> shift) & 1 for shift in range(length - 1, -1, -1))

    append(0b0100, 4)                                  # byte mode
    append(len(data), 8 if version <= 9 else 16)
    for byte in data:
        append(byte, 8)

    capacity = _data_codewords(version, level) * 8
    append(0, min(4, capacity - len(bits)))            # terminator
    append(0, -len(bits) % 8)
    pad = 0xEC
    while len(bits) < capacity:
        append(pad, 8)
        pad ^= 0xEC ^ 0x11

    return [int("".join(map(str, bits[index:index + 8])), 2)
            for index in range(0, len(bits), 8)]


def choose_version(text, level):
    length = len(text.encode("utf-8"))
    for version in range(MIN_VERSION, MAX_VERSION + 1):
        header = 4 + (8 if version <= 9 else 16)
        if header + length * 8 <= _data_codewords(version, level) * 8:
            return version
    raise QRCodeError("the text is too long for a QR code at this error correction level")


# Matrix ---
class _Matrix(object):

    def __init__(self, version):
        self.version = version
        self.size = version * 4 + 17
        self.modules = [[False] * self.size for _ in range(self.size)]
        self.function = [[False] * self.size for _ in range(self.size)]

    def set_function(self, x, y, dark):
        self.modules[y][x] = dark
        self.function[y][x] = True

    def draw_function_patterns(self):
        size = self.size
        for index in range(size):
            self.set_function(6, index, index % 2 == 0)
            self.set_function(index, 6, index % 2 == 0)

        for x, y in ((3, 3), (size - 4, 3), (3, size - 4)):
            self._draw_finder(x, y)

        positions = _alignment_positions(self.version)
        last = len(positions) - 1
        for i, x in enumerate(positions):
            for j, y in enumerate(positions):
                # not over the finders
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set_function(x + dx, y + dy, max(abs(dx), abs(dy)) != 1)

        self.draw_format_bits(0, "L")    # reserved now, written for real later
        self._draw_version()

    def _draw_finder(self, cx, cy):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < self.size and 0 <= y < self.size:
                    distance = max(abs(dx), abs(dy))
                    self.set_function(x, y, distance not in (2, 4))

    def draw_format_bits(self, mask, level):
        data = _FORMAT_BITS[level] << 3 | mask
        remainder = data
        for _ in range(10):
            remainder = (remainder << 1) ^ ((remainder >> 9) * 0x537)
        bits = (data << 10 | remainder) ^ 0x5412

        bit = lambda index: (bits >> index) & 1 != 0
        size = self.size
        for index in range(6):
            self.set_function(8, index, bit(index))
        self.set_function(8, 7, bit(6))
        self.set_function(8, 8, bit(7))
        self.set_function(7, 8, bit(8))
        for index in range(9, 15):
            self.set_function(14 - index, 8, bit(index))

        for index in range(8):
            self.set_function(size - 1 - index, 8, bit(index))
        for index in range(8, 15):
            self.set_function(8, size - 15 + index, bit(index))
        self.set_function(8, size - 8, True)       # the dark module

    def _draw_version(self):
        if self.version < 7:
            return
        remainder = self.version
        for _ in range(12):
            remainder = (remainder << 1) ^ ((remainder >> 11) * 0x1F25)
        bits = self.version << 12 | remainder
        for index in range(18):
            dark = (bits >> index) & 1 != 0
            a = self.size - 11 + index % 3
            b = index // 3
            self.set_function(a, b, dark)
            self.set_function(b, a, dark)

    def draw_codewords(self, codewords):
        size = self.size
        bit_index = 0
        total = len(codewords) * 8
        right = size - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vertical in range(size):
                for column in range(2):
                    x = right - column
                    upward = ((right + 1) & 2) == 0
                    y = size - 1 - vertical if upward else vertical
                    if not self.function[y][x] and bit_index < total:
                        self.modules[y][x] = (codewords[bit_index >> 3] >> (7 - (bit_index & 7))) & 1 != 0
                        bit_index += 1
            right -= 2

    def apply_mask(self, mask):
        conditions = (
            lambda x, y: (x + y) % 2 == 0,
            lambda x, y: y % 2 == 0,
            lambda x, y: x % 3 == 0,
            lambda x, y: (x + y) % 3 == 0,
            lambda x, y: (x // 3 + y // 2) % 2 == 0,
            lambda x, y: x * y % 2 + x * y % 3 == 0,
            lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
            lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
        )
        condition = conditions[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.function[y][x] and condition(x, y):
                    self.modules[y][x] = not self.modules[y][x]

    def penalty(self):
        size = self.size
        modules = self.modules
        score = 0

        def line_penalty(line):
            result = 0
            run_colour, run = line[0], 1
            for dark in line[1:]:
                if dark == run_colour:
                    run += 1
                else:
                    if run >= 5:
                        result += run - 2
                    run_colour, run = dark, 1
            if run >= 5:
                result += run - 2
            # finder-like 1:1:3:1:1 runs with four light modules on a side
            text = "".join("1" if dark else "0" for dark in line)
            padded = "0000" + text + "0000"
            start = padded.find("1011101")
            while start != -1:
                before = padded[max(0, start - 4):start]
                after = padded[start + 7:start + 11]
                if before == "0000" or after == "0000":
                    result += 40
                start = padded.find("1011101", start + 1)
            return result

        for row in modules:
            score += line_penalty(row)
        for x in range(size):
            score += line_penalty([modules[y][x] for y in range(size)])

        for y in range(size - 1):
            for x in range(size - 1):
                colour = modules[y][x]
                if colour == modules[y][x + 1] == modules[y + 1][x] == modules[y + 1][x + 1]:
                    score += 3

        dark = sum(sum(row) for row in modules)
        total = size * size
        score += (abs(dark * 20 - total * 10) + total - 1) // total * 10 - 10
        return score


def encode(text, level="M"):
    """The QR code for `text`, as rows of booleans - True is a dark module.

    Args:
        text (str): What the code says.
        level (str): Error correction, "L", "M", "Q" or "H".

    Raises:
        QRCodeError: When the text doesn't fit in any version.
    """
    if level not in ERROR_LEVELS:
        raise QRCodeError(f"unknown error correction level {level!r}")
    version = choose_version(text, level)
    codewords = _add_error_correction(_encode_data(text, version, level), version, level)

    best = None
    for mask in range(8):
        matrix = _Matrix(version)
        matrix.draw_function_patterns()
        matrix.draw_codewords(codewords)
        matrix.apply_mask(mask)
        matrix.draw_format_bits(mask, level)
        score = matrix.penalty()
        if best is None or score < best[0]:
            best = (score, matrix)
    return best[1].modules
