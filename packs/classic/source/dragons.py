"""The classic pack's dragons - Rhindle (red), Yorgle (yellow) and Grundle (green): one drawing per pose,
16x40, in each dragon's two colours. K = black outline, B = body, H = highlight.

The shapes were first traced from Stable Diffusion silhouettes of the original 2600 dragon; this text art is
the source now. The defeated dragon isn't drawn: it's the normal pose upside down (as the 2600 does), feet
down on the bottom row.

Usage: .venv/bin/python packs/classic/source/dragons.py   -> packs/classic/cast/dragon_<pose>_<colour>.png
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))  # the repo root
from content.pictures import save_folder
from shared.palettes import BLACK, NES
from shared.pixelart import from_ascii

COLOURS = {"red": (0x16, 0x26), "yellow": (0x28, 0x38), "green": (0x1A, 0x2A)}  # body, highlight (NES palette)

NORMAL = """
................
................
...........K....
..........KBK...
.........KHHK...
........KBHHHK..
.......KKBHBBK..
....K.KKBBBBBK..
..KKBKKBHHHHBHK.
.KBBHHHHHHHHBHHK
KKBBHHHHKHHBBBK.
KBHHHHHHBBBBBKK.
.KBBBBBBBBBBKK..
..KKKKKKKBKBKK..
........KKBBBK..
.........KBBBK..
.........KBBKK..
.......KKKBBBK..
......KKKKBBBK..
....KKBBBBBBBKK.
...KKBBBHHHHBKKK
..KKBHHHHHHHBBKK
.KKBHHHHBHHBBBKK
KKBBHBBBKKKBBBBK
KBBBBBKK..KBHBBK
KBBBBK....KBBBBK
KBHHBK....KBBBBK
KBHHBK...KKBHHBK
KBHHBBKKKKBHHBBK
KBBBBBBBBBBBBBBK
.KBBHHHHHHBBBBK.
.KBBBBBBBHBBKK..
..KKBBBKBBBK....
...KBBBKBBKKKKK.
..K.KBKKBBBBBBBK
.KBKKBBKBBBBBBBK
.KBBBBBBKKKKBBBK
..KKBBBBBHHHBHBK
....KBBBBBBBBBK.
.....KKKKKKKKK.."""

ROAR = """
.KK.............
KBBK............
KBBK............
KBKBK...........
.KKBKKKKKKKK....
...KBKHHHHKKKK..
....KHHHKBHKKKK.
.....KHHHKHBBBK.
......KKKHHBBKK.
......KKKBBBKK..
.....KKKHHBKK...
.....KHHHBKKK...
....KKBBKKKKK...
...KKKKKKBBK....
..KBKK.KBBBK....
.KKBBK.KKBKKK...
KKKBK.KKBBBKK...
KKBK.KKBBHBBKK..
.KK.KKBHHHBBKK..
...KBBHBHHBBBKK.
...KBHHBHHBBBKK.
..KBBHHHBHBBBBK.
..KBHHBBBBBBBBK.
..KBHHBBBBBBBBK.
..KBHBHBBBBBBBK.
..KBHHHBBBHBBBK.
..KBHHBHBBHBBBK.
..KKBHHHBBBBBBK.
...KBHHHHHBBKK..
...KBBBBHHBBK...
....KKBBBBBK....
..KKKBBHHBK.....
.KBBBBHHBK......
KBBBBBBKK.......
KBBKKKKK........
KHBKK...........
KHBKBK..........
KBHHHBK.........
KBBBHHK.........
.KKKKK.........."""


def upside_down(art):
    """The art flipped top to bottom, then moved down so its lowest pixel is on the last row."""
    rows = art.strip("\n").split("\n")[::-1]
    while rows and set(rows[-1]) == {"."}:
        rows = [rows.pop()] + rows
    return "\n".join(rows)


def pictures():
    out = {}
    for colour, (body, light) in COLOURS.items():
        palette = {"K": NES[BLACK], "B": NES[body], "H": NES[light]}
        for pose, art in (("normal", NORMAL), ("roar", ROAR), ("dead", upside_down(NORMAL))):
            out[f"dragon_{pose}_{colour}"] = from_ascii(art, palette)
    return out


if __name__ == "__main__":
    save_folder(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cast"), pictures())
