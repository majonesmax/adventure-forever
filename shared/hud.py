"""NES-style text and screens: a hand-drawn 5x7 pixel font in 8x8 cells, the status bar, the title screen
(replaces the 2600's game-number room $00) and the win banner (chalice home in room $12).
"""

import numpy as np

from engine import rooms as R

_FONT = """
A .###. #...# #...# ##### #...# #...# #...#
B ####. #...# #...# ####. #...# #...# ####.
C .#### #.... #.... #.... #.... #.... .####
D ####. #...# #...# #...# #...# #...# ####.
E ##### #.... #.... ####. #.... #.... #####
F ##### #.... #.... ####. #.... #.... #....
G .#### #.... #.... #..## #...# #...# .####
H #...# #...# #...# ##### #...# #...# #...#
I ##### ..#.. ..#.. ..#.. ..#.. ..#.. #####
J ....# ....# ....# ....# #...# #...# .###.
K #...# #..#. #.#.. ##... #.#.. #..#. #...#
L #.... #.... #.... #.... #.... #.... #####
M #...# ##.## #.#.# #.#.# #...# #...# #...#
N #...# ##..# #.#.# #..## #...# #...# #...#
O .###. #...# #...# #...# #...# #...# .###.
P ####. #...# #...# ####. #.... #.... #....
Q .###. #...# #...# #...# #.#.# #..#. .##.#
R ####. #...# #...# ####. #.#.. #..#. #...#
S .#### #.... #.... .###. ....# ....# ####.
T ##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..
U #...# #...# #...# #...# #...# #...# .###.
V #...# #...# #...# #...# #...# .#.#. ..#..
W #...# #...# #...# #.#.# #.#.# ##.## #...#
X #...# #...# .#.#. ..#.. .#.#. #...# #...#
Y #...# #...# .#.#. ..#.. ..#.. ..#.. ..#..
Z ##### ....# ...#. ..#.. .#... #.... #####
0 .###. #...# #..## #.#.# ##..# #...# .###.
1 ..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.
2 .###. #...# ....# ...#. ..#.. .#... #####
3 ####. ....# ....# .###. ....# ....# ####.
4 ...#. ..##. .#.#. #..#. ##### ...#. ...#.
5 ##### #.... ####. ....# ....# ....# ####.
6 .###. #.... #.... ####. #...# #...# .###.
7 ##### ....# ...#. ..#.. .#... .#... .#...
8 .###. #...# #...# .###. #...# #...# .###.
9 .###. #...# #...# .#### ....# ....# .###.
! ..#.. ..#.. ..#.. ..#.. ..#.. ..... ..#..
. ..... ..... ..... ..... ..... ..... ..#..
, ..... ..... ..... ..... ..... ..#.. .#...
- ..... ..... ..... .###. ..... ..... .....
: ..... ..#.. ..... ..... ..... ..#.. .....
' ..#.. ..#.. ..... ..... ..... ..... .....
? .###. #...# ....# ...#. ..#.. ..... ..#..
< ...#. ..#.. .#... #.... .#... ..#.. ...#.
> .#... ..#.. ...#. ....# ...#. ..#.. .#...
"""
GLYPHS = {" ": "." * 35}
for _line in _FONT.strip().split("\n"):
    _ch, *_rows = _line.split(" ")
    assert len(_rows) == 7 and all(len(r) == 5 for r in _rows), _line
    GLYPHS[_ch] = "".join(_rows)
GLYPHS.update({  # a few more, for DOS prompts and paths (a backslash can't sit in the table above)
    "\\": "#...." "#...." ".#..." "..#.." "...#." "....#" "....#",
    "/": "....#" "....#" "...#." "..#.." ".#..." "#...." "#....",
    "_": "....." "....." "....." "....." "....." "....." "#####"})


def text_width(text, scale=1):
    return len(text) * 8 * scale


def draw_text(img, text, x, y, colour, scale=1, shadow=(0, 0, 0)):
    """Draw text on an HxWx3 uint8 image (NES-style: 5x7 glyphs in 8x8 cells, 1 px drop shadow)."""
    for layer, (dx, dy, col) in enumerate(((1, 1, shadow), (0, 0, colour))):
        if col is None:
            continue
        for i, ch in enumerate(text.upper()):
            g = GLYPHS.get(ch, GLYPHS["?"])
            for gy in range(7):
                for gx in range(5):
                    if g[gy * 5 + gx] == "#":
                        px = x + (i * 8 + gx) * scale + dx * scale
                        py = y + gy * scale + dy * scale
                        img[max(py, 0):max(py + scale, 0), max(px, 0):max(px + scale, 0)] = col


def frame_box(img, x0, y0, x1, y1, colour):
    """A 1 px NES-style frame with cut corners."""
    img[y0, x0 + 1:x1] = colour
    img[y1, x0 + 1:x1] = colour
    img[y0 + 1:y1, x0] = colour
    img[y0 + 1:y1, x1] = colour


def mini_room(room, wall_rgb, floor_rgb, cell_w=2, half_row=4):
    """A tiny drawing of a room's walls (for the title screen's castle)."""
    heights = [half_row, 2 * half_row, 2 * half_row, 2 * half_row, 2 * half_row, 2 * half_row, half_row]
    out = np.zeros((sum(heights), R.COLS * cell_w, 3), np.uint8)
    out[:] = floor_rgb
    y = 0
    for r, hh in enumerate(heights):
        for c, b in enumerate(room["grid"][r]):
            if b:
                out[y:y + hh, c * cell_w:(c + 1) * cell_w] = wall_rgb
        y += hh
    return out
