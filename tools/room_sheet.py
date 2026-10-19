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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, as a script
from engine import rooms as R

from engine import paths
from shared.types import Rgb

HERE = paths.ROOT
ROW_LINES = [last - first + 1 for first, last in R.ROW_LINES]  # scan lines per wall row (measured)
FLOOR_GREY = (162, 162, 161)               # the 2600's floor, around the walls
CELL_W, SCALE_Y = 8, 1                     # 40 columns x 8 px = 320 wide; 2600 pixels are 2:1


def wall_rgb(room_number: int, room: dict[str, Any]) -> Rgb:
    if room["colour"] == 0x08:
        return (70, 70, 80)
    path = os.path.join(HERE, "shots", "rooms", f"room_{room_number:02X}.png")
    if not os.path.exists(path):
        return (0, 0, 0)
    pixels = np.array(Image.open(path))[13:207].reshape(-1, 3)
    pixels = pixels[np.abs(pixels.astype(int) - FLOOR_GREY).max(axis=1) >= 8]
    colours, counts = np.unique(pixels, axis=0, return_counts=True)
    red, green, blue = (int(channel) for channel in colours[np.argmax(counts)])
    return red, green, blue


def draw_room(room: dict[str, Any]) -> Image.Image:
    width, height = R.COLS * CELL_W, sum(ROW_LINES) * SCALE_Y
    picture = Image.new("RGB", (width, height), FLOOR_GREY)
    pen = ImageDraw.Draw(picture)
    colour = wall_rgb(room["room"], room)
    y = 0
    for row, lines in enumerate(ROW_LINES):
        for column, is_wall in enumerate(room["grid"][row]):
            if is_wall:
                corners = [column * CELL_W, y, (column + 1) * CELL_W - 1, y + lines * SCALE_Y - 1]
                pen.rectangle(corners, fill=colour)
        y += lines * SCALE_Y
    sheet_pixels = CELL_W // 4  # sheet pixels per frame pixel
    for flag, (x0, x1) in (("thin_wall_left", R.THIN_WALL_LEFT_X), ("thin_wall_right", R.THIN_WALL_RIGHT_X)):
        if room[flag]:
            pen.rectangle([x0 * sheet_pixels, 0, (x1 + 1) * sheet_pixels - 1, height - 1], fill=colour)
    return picture


def label(pen: ImageDraw.ImageDraw, room: dict[str, Any], x: int, y: int, font: Any) -> None:
    """A room's number and name, and its exits (and whether it's dark), above its picture."""
    exits = room["exits"][1]
    pen.text((x, y), f"${room['room']:02X} {room['name']}", fill=(235, 235, 235), font=font)
    exit_list = " ".join(f"{direction[0].upper()}:{target:02X}" for direction, target in exits.items())
    dark = "  (dark)" if room["colour"] == 0x08 else ""
    pen.text((x, y + 15), exit_list + dark, fill=(150, 150, 170), font=font)


def main() -> None:
    rooms = R.decode_all()[1:]
    font = ImageFont.load_default()
    columns, pad, label_height = 5, 14, 34
    tile_width, tile_height = R.COLS * CELL_W, sum(ROW_LINES) * SCALE_Y
    sheet_rows = (len(rooms) + columns - 1) // columns
    sheet_size = (columns * (tile_width + pad) + pad, sheet_rows * (tile_height + label_height + pad) + pad)
    sheet = Image.new("RGB", sheet_size, (24, 24, 32))
    pen = ImageDraw.Draw(sheet)
    for index, room in enumerate(rooms):
        x = pad + (index % columns) * (tile_width + pad)
        y = pad + (index // columns) * (tile_height + label_height + pad)
        sheet.paste(draw_room(room), (x, y + label_height))
        label(pen, room, x, y, font)
    out = os.path.join(HERE, "shots", "room_sheet.png")
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
