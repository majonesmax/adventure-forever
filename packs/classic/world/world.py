"""The classic world's castle gates: an iron portcullis at the gate's current height - vertical bars, a
crossbar every 6 px, spikes at the bottom (drawn in code: the crossbars stay put as the gate rises).
"""

import numpy as np

from content.world import World
from shared.palettes import NES

BLACK, GREY = 0x0F, 0x10  # NES colours


class CustomWorld(World):
    def gate(self, castle, w, h):
        return portcullis(w, h) if h > 0 else None


def portcullis(w, h):
    """Iron portcullis of the original's current height: vertical bars, a crossbar every 6 px, spikes at
    the bottom."""
    out = np.zeros((h, w, 4), np.uint8)
    iron, highlight, black = (*NES[GREY], 255), (*NES[0x00], 255), (*NES[BLACK], 255)
    out[:, :] = black
    for x in range(1, w - 1, 3):
        out[:, x] = iron
        out[:, x + 1:x + 2] = highlight if x + 1 < w - 1 else black
    for y in range(2, h, 6):
        out[y, 1:w - 1] = iron
    if h >= 4:
        out[h - 2:, :] = 0
        for x in range(1, w - 1, 3):
            out[h - 2:, x] = iron  # spike tips poke out below
    return out
