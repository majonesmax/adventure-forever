"""The "whole room" screen layout both built-in looks use - the original's whole room always visible:

    +---------------------------------+  0
    |  status bar (HUD)               |
    +--+---------------------------+--+  48 = HUD_H
    |  |  the room, 240 x 192      |  |      one 2600 playfield column = 6 px (COL_W), one half-row
    |  |  (40 columns x 7 rows)    |  |      of the room = 16 px; the room sits at x = 8 (ROOM_X)
    +--+---------------------------+--+  240
    0  8                          248 256

Positions in the game are in the 2600's own frame (160 px wide, scan lines 13-205); to_room() converts
them to pixels inside the room area.
"""

import numpy as np

from engine import rooms as R

SCREEN_W, SCREEN_H = 256, 240
HUD_H, ROOM_X, ROOM_H, COL_W = 48, 8, 192, 6
ROOM_W = R.COLS * COL_W  # 240
ROOM_RECT = (ROOM_X, HUD_H, ROOM_W, ROOM_H)  # x, y, w, h on the screen


def to_room(fx, line, col_w=COL_W):
    """2600 frame coordinates (160 px wide, scan lines 13-205) -> room-space pixels."""
    return fx * col_w / 4, (line - 13) * ROOM_H / 193


def wall_mask(room, col_w=COL_W):
    """Where the room's walls are, at layout resolution: True = wall. Columns -> col_w px, half-rows -> 16 px."""
    m = np.zeros((ROOM_H, R.COLS * col_w), bool)
    heights = [16, 32, 32, 32, 32, 32, 16]  # 7 ROM rows = half, 5 full, half
    y = 0
    for r, hh in enumerate(heights):
        for c, b in enumerate(room["grid"][r]):
            if b:
                m[y:y + hh, c * col_w:(c + 1) * col_w] = True
        y += hh
    for flag, (x0, _) in (("thin_wall_left", R.THIN_WALL_LEFT_X), ("thin_wall_right", R.THIN_WALL_RIGHT_X)):
        if room[flag]:
            fx = int(round(x0 * col_w / 4))
            m[:, fx:fx + max(4, col_w * 2 // 3)] = True  # 4 px: outline both sides + 2 px of wall texture
    return m
