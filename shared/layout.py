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

from typing import Any

import numpy as np

from engine import rooms as R
from shared.types import Mask

SCREEN_W, SCREEN_H = 256, 240
HUD_H, ROOM_X, ROOM_H, COL_W = 48, 8, 192, 6
ROOM_W = R.COLS * COL_W  # 240
ROOM_RECT = (ROOM_X, HUD_H, ROOM_W, ROOM_H)  # x, y, w, h on the screen
ROOM_FIRST_LINE, ROOM_LINES = 13, 193  # the 2600 draws a room on TV scan lines 13-205
ROW_HEIGHTS = [16, 32, 32, 32, 32, 32, 16]  # the room's 7 rows of wall, in our pixels: half, 5 full, half


def to_room(frame_x: float, line: float, col_w: int = COL_W) -> tuple[float, float]:
    """2600 frame coordinates (160 px wide, scan lines 13-205) -> room-space pixels. Across, 4 of the 2600's
    pixels make one wall column (col_w of ours); down, the room's 193 scan lines squeeze into ROOM_H."""
    return frame_x * col_w / 4, (line - ROOM_FIRST_LINE) * ROOM_H / ROOM_LINES


def wall_mask(room: dict[str, Any], col_w: int = COL_W) -> Mask:
    """Where the room's walls are, at layout resolution: True = wall. Each wall column -> col_w px; each of
    the 7 rows -> ROW_HEIGHTS."""
    walls = np.zeros((ROOM_H, R.COLS * col_w), bool)
    top = 0
    for row, height in enumerate(ROW_HEIGHTS):
        for column, is_wall in enumerate(room["grid"][row]):
            if is_wall:
                walls[top:top + height, column * col_w:(column + 1) * col_w] = True
        top += height
    thin_walls = (("thin_wall_left", R.THIN_WALL_LEFT_X), ("thin_wall_right", R.THIN_WALL_RIGHT_X))
    for flag, (frame_x, _) in thin_walls:  # the narrow walls some mazes have, between the columns
        if room[flag]:
            left = int(round(frame_x * col_w / 4))
            walls[:, left:left + max(4, col_w * 2 // 3)] = True  # 4 px: outline both sides + 2 px of wall
    return walls
