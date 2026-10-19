"""Draw every room from rooms.py alone (no emulator) as flat placeholder tiles: a contact sheet of the world.
Wall colours are the real ones, sampled from the frames verify_rooms.py saved (shots/rooms/room_XX.png);
the dark rooms (catacombs, black maze) get a dark grey so their layout shows.

Usage: python room_sheet.py  -> shots/room_sheet.png
"""

import os
import sys
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, when run as a script
from engine import rooms as R

from engine import paths
from shared.types import Rgb

HERE = paths.ROOT
ROW_LINES = [b - a + 1 for a, b in R.ROW_LINES]  # scan lines per wall row (measured)
BG = (162, 162, 161)
CELL_W, SCALE_Y = 8, 1                     # 40 columns x 8 px = 320 wide; 2600 pixels are 2:1


def wall_rgb(n: int, room: dict[str, Any]) -> Rgb:
    if room["colour"] == 0x08:
        return (70, 70, 80)
    path = os.path.join(HERE, "shots", "rooms", f"room_{n:02X}.png")
    if not os.path.exists(path):
        return (0, 0, 0)
    f = np.array(Image.open(path))[13:207].reshape(-1, 3)
    f = f[np.abs(f.astype(int) - BG).max(axis=1) >= 8]
    vals, counts = np.unique(f, axis=0, return_counts=True)
    red, green, blue = (int(v) for v in vals[np.argmax(counts)])
    return red, green, blue


def draw_room(room: dict[str, Any]) -> Image.Image:
    w, h = R.COLS * CELL_W, sum(ROW_LINES) * SCALE_Y
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    colour = wall_rgb(room["room"], room)
    y = 0
    for r, lines in enumerate(ROW_LINES):
        for c, b in enumerate(room["grid"][r]):
            if b:
                d.rectangle([c * CELL_W, y, (c + 1) * CELL_W - 1, y + lines * SCALE_Y - 1], fill=colour)
        y += lines * SCALE_Y
    px = CELL_W // 4  # sheet pixels per frame pixel
    for flag, (x0, x1) in (("thin_wall_left", R.THIN_WALL_LEFT_X), ("thin_wall_right", R.THIN_WALL_RIGHT_X)):
        if room[flag]:
            d.rectangle([x0 * px, 0, (x1 + 1) * px - 1, h - 1], fill=colour)
    return im


def main() -> None:
    rooms = R.decode_all()[1:]
    font = ImageFont.load_default()
    cols, pad, label_h = 5, 14, 34
    tw, th = R.COLS * CELL_W, sum(ROW_LINES) * SCALE_Y
    sheet_rows = (len(rooms) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, sheet_rows * (th + label_h + pad) + pad), (24, 24, 32))
    d = ImageDraw.Draw(sheet)
    for i, room in enumerate(rooms):
        x = pad + (i % cols) * (tw + pad)
        y = pad + (i // cols) * (th + label_h + pad)
        sheet.paste(draw_room(room), (x, y + label_h))
        ex = room["exits"][1]
        d.text((x, y), f"${room['room']:02X} {room['name']}", fill=(235, 235, 235), font=font)
        d.text((x, y + 15), " ".join(f"{k[0].upper()}:{v:02X}" for k, v in ex.items())
               + ("  (dark)" if room["colour"] == 0x08 else ""), fill=(150, 150, 170), font=font)
    out = os.path.join(HERE, "shots", "room_sheet.png")
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
