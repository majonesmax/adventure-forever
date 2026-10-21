"""The pbj world's scenery (world.py): every room painted from the game's wall grid in a theme.

  - themed walls (THEMES: candy / ice / fire / grass / forest / dungeon / crypt / crystal / secret + castle
    interiors): the wall grid with rounded corners (blur + threshold, radius 3 - 6 px maze walls keep their
    width; thin walls OR'd back), a top with specks and a light rim, darker side strips, a 10 px patterned
    front face (wafer / ice bricks / glowing cracks / rock strata / leaves / bricks / facets) with drips over
    its top (icing / snow / lava / grass / moss / ...), line art in the theme's dark colour, a tinted floor
    shadow; castle battlements keep their exact shape and get caps (gumdrops / ice spikes / flames).
  - ground: a supplied tile (grass) or the theme's procedural floor (snow, scorched earth, dirt, flagstones,
    palace checker) with big soft light/dark patches; decorations per theme, deterministic per room.
    No decoration is grey: the only grey speck in the game must be the hidden dot.
  - gate_sprite: a castle portcullis in its castle's theme.
Walls stay where the game has them - only corners are rounded by a few pixels, gameplay unchanged.
"""

from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from shared import layout as L
from shared.pixelart import blit, shade, snes_rgb
from shared.types import Floats, Mask, Picture, Rgb

Grid = np.ndarray   # a whole number per pixel: coordinates, hashes, depths
Colours = dict[str, Floats]   # a theme's named colours, as float RGB (painting works in floats)

OUTLINE = (32, 32, 48)  # the dark line around decorations
DECALS = {
    # candy theme (grass)
    "tuft": ("""
.g...g.
.gG.Gg.
..gGg.g
g.GGG.G
.GGgGG.""", {"g": (56, 128, 40), "G": (120, 200, 64)}),
    "flower": ("""
.P.
PYP
.P.
.g.""", {"P": (248, 160, 200), "Y": (248, 224, 64), "g": (56, 128, 40)}),
    "flower2": ("""
.W.
WYW
.W.
.g.""", {"W": (248, 248, 248), "Y": (248, 200, 40), "g": (56, 128, 40)}),
    "mint": ("""
.dd.
dRWd
dWRd
.dd.""", {"R": (224, 40, 56), "W": (248, 248, 248), "d": (136, 32, 48)}),
    "rock": ("""
.ll.
lLLd
dLdd
.dd.""", {"L": (168, 124, 84), "l": (208, 172, 124), "d": (104, 72, 48)}),  # warm brown, never dot-grey
    # ice theme (snow)
    "mound": ("""
..WW..
.WWWWb
WWWWbb""", {"W": (248, 252, 255), "b": (184, 208, 240)}),
    "crystal": ("""
.c.
cCc
.c.""", {"C": (248, 252, 255), "c": (120, 184, 240)}),
    "penguin": ("""
.KKK.
KWKWK
KKYKK
KWWWK
KWWWK
.KWK.
.Y.Y.""", {"K": OUTLINE, "W": (248, 248, 248), "Y": (248, 152, 32)}),
    "ice_rock": ("""
.ll.
lLLd
dLdd
.dd.""", {"L": (152, 176, 208), "l": (208, 224, 248), "d": (88, 112, 160)}),
    # fire kingdom (scorched ground)
    "ember": ("""
.o.
oYo
.o.""", {"o": (232, 96, 32), "Y": (248, 216, 72)}),
    "flame": ("""
..o..
.oYo.
oYWYo
oYYYo
.ooo.""", {"o": (232, 88, 32), "Y": (248, 200, 48), "W": (255, 248, 200)}),
    "char_rock": ("""
.ll.
lLLd
dLod
.dd.""", {"L": (88, 64, 72), "l": (128, 96, 104), "d": (48, 32, 40), "o": (248, 120, 32)}),
    "dead_tuft": ("""
.g...g.
.gG.Gg.
..gGg.g
g.GGG.G""", {"g": (112, 56, 32), "G": (176, 96, 48)}),
    # forest / dungeon / crypt / crystal
    "mushroom": ("""
.KKK.
KRWRK
KRRRK
.KwK.
.KwK.""", {"K": (56, 24, 24), "R": (216, 48, 48), "W": (248, 248, 248), "w": (232, 216, 184)}),
    "bones": ("""
W.....W
.WWWWW.
W.....W""", {"W": (224, 216, 192)}),
    "skull": ("""
.WWW.
WKWKW
WWWWW
.WKW.""", {"W": (224, 216, 192), "K": (40, 32, 32)}),
    "shard": ("""
..L.
.LPd
.PPd
LPdd""", {"L": (240, 216, 252), "P": (184, 128, 232), "d": (112, 64, 168)}),
    "pebble": ("""
.ll.
lLLd
.dd.""", {"L": (140, 108, 80), "l": (176, 140, 104), "d": (92, 68, 52)}),  # brown: grey is for the dot
}

# battlement caps, one per merlon (C = cap colour, h = highlight, K = its dark shade)
CAPS = {
    "candy": ("""
..KK..
.KhCK.
KhCCCK
KCCCCK
KCCCCK
.KKKK.""", [(232, 56, 72), (96, 200, 72), (248, 200, 48), (168, 88, 216)]),
    "ice": ("""
..KK..
.KhCK.
.KhCK.
KhhCCK
KhCCCK
KhCCCK
.KKKK.""", [(160, 216, 248)]),
    "fire": ("""
..K...
..KK..
.KhK..
.KhCK.
KhWCCK
KhWWCK
.KCCK.
..KK..""", [(248, 136, 32)]),
}

def text_art(art: str, colours: dict[str, Rgb]) -> Picture:
    """Text art ("." clear) -> an RGBA picture."""
    rows = art.strip("\n").split("\n")
    picture = np.zeros((len(rows), len(rows[0]), 4), np.uint8)
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char != ".":
                picture[y, x] = (*colours[char], 255)
    return picture


def decal(name: str) -> Picture:
    art, colours = DECALS[name]
    return text_art(art, colours)


def rounded_mask(walls: Mask, radius: int = 4) -> Mask:
    """Round the corners of a wall mask: blur, re-threshold. Edges replicate so walls touching the screen
    edge stay straight there."""
    margin = radius * 3
    big = np.pad(walls.astype(np.uint8) * 255, margin, mode="edge")
    blurred = Image.fromarray(big).filter(ImageFilter.GaussianBlur(radius))
    soft = np.array(blurred)[margin:-margin, margin:-margin]
    return soft >= 115  # a touch under half: 1-column (6 px) maze walls keep their full width


def face_depth(walls: Mask, yy: Grid, face_h: int) -> Grid:
    """For wall pixels: how far down to open floor (1..face_h), 0 elsewhere = the front-face band."""
    h = walls.shape[0]
    depth = np.zeros(walls.shape, int)
    for distance in range(face_h, 0, -1):
        depth[walls & ~np.roll(walls, -distance, axis=0) & (yy < h - distance)] = distance
    return depth


# Wall themes. drip = what runs over the face top (icing / snow / lava); face pattern per theme.
THEMES = {
    "candy": {"top": (240, 160, 200), "top_hi": (248, 176, 216), "top_lo": (232, 148, 192),
              "rim": (252, 216, 236),
              "face": (200, 96, 152), "stripe": (168, 72, 128), "stripe_hi": (224, 128, 176),
              "face_foot": (136, 48, 104), "drip": (248, 240, 248), "drip_sh": (216, 200, 232),
              "line": (104, 32, 72),
              "specks": [(248, 248, 248), (248, 224, 64), (96, 208, 240), (232, 56, 72), (120, 216, 96)],
              "face_pattern": "wafer", "shadow": (0.72, 0.68, 0.82), "title": (236, 174, 212),
              "decals": ["tuft"] * 6 + ["flower"] * 2 + ["flower2"] * 2 + ["mint", "rock"]},
    "ice": {"top": (144, 196, 240), "top_hi": (168, 212, 244), "top_lo": (128, 184, 232),
            "rim": (216, 240, 252),
            "face": (104, 168, 224), "stripe": (72, 128, 200), "stripe_hi": (176, 224, 248),
            "face_foot": (56, 96, 168), "drip": (248, 252, 255), "drip_sh": (208, 224, 240),
            "line": (40, 64, 136),
            "specks": [(255, 255, 255), (152, 208, 248)], "face_pattern": "ice_blocks",
            "shadow": (0.8, 0.86, 0.96), "title": (168, 216, 248),
            "floor": ((236, 244, 252), (216, 232, 248), (196, 220, 244)),
            "decals": ["mound"] * 6 + ["crystal"] * 4 + ["penguin"] + ["ice_rock"]},
    "fire": {"top": (88, 56, 72), "top_hi": (104, 64, 80), "top_lo": (76, 48, 64), "rim": (136, 88, 96),
             "face": (64, 40, 56), "stripe": (232, 96, 32), "stripe_hi": (248, 176, 56),
             "face_foot": (40, 24, 40), "drip": (248, 136, 32), "drip_sh": (216, 72, 24),
             "line": (32, 16, 32),
             "drip_core": (248, 216, 72), "specks": [(248, 152, 40), (248, 216, 72)],
             "face_pattern": "cracks",
             "shadow": (0.7, 0.58, 0.58), "title": (248, 152, 56),
             "floor": ((128, 68, 48), (148, 80, 52), (104, 56, 44)),
             "decals": ["ember"] * 4 + ["flame"] * 2 + ["char_rock"] * 3 + ["dead_tuft"] * 3},
    # green rooms outside: grassy cliffs like the DS overworld (grass on top, brown rock face, grass overhang)
    "grass": {"top": (120, 208, 80), "top_hi": (136, 216, 96), "top_lo": (104, 192, 72),
              "rim": (176, 232, 120),
              "face": (160, 112, 72), "stripe": (120, 80, 48), "stripe_hi": (192, 144, 96),
              "face_foot": (88, 56, 40), "drip": (104, 192, 72), "drip_sh": (64, 144, 48),
              "line": (48, 72, 32),
              "specks": [(248, 248, 248), (248, 224, 64)], "face_pattern": "rock",
              "shadow": (0.74, 0.8, 0.7), "title": (136, 216, 96), "caps": None,
              "decals": ["tuft"] * 6 + ["flower"] * 2 + ["flower2"] * 2 + ["rock"] * 2},
    # blue labyrinth: a hedge maze in the woods, dirt paths
    "forest": {"top": (48, 120, 64), "top_hi": (64, 144, 72), "top_lo": (40, 104, 56), "rim": (96, 176, 88),
               "face": (32, 88, 48), "stripe": (24, 60, 32), "stripe_hi": (64, 128, 64),
               "face_foot": (16, 40, 24), "drip": (64, 144, 72), "drip_sh": (40, 104, 48),
               "line": (16, 40, 24),
               "specks": [(232, 72, 72), (248, 248, 248)], "face_pattern": "leaves",
               "shadow": (0.7, 0.72, 0.66), "title": (120, 208, 96), "caps": None,
               "floor": ((200, 168, 112), (216, 188, 132), (176, 144, 96)),
               "decals": ["tuft"] * 3 + ["mushroom"] * 2 + ["rock"] * 2 + ["flower2"]},
    # red maze + top entry room 2: an old stone dungeon with moss
    "dungeon": {"top": (120, 120, 140), "top_hi": (136, 136, 156), "top_lo": (108, 108, 128),
                "rim": (168, 168, 188),
                "face": (88, 88, 108), "stripe": (60, 60, 80), "stripe_hi": (124, 124, 144),
                "face_foot": (44, 44, 60), "drip": (96, 160, 72), "drip_sh": (64, 120, 56),
                "line": (28, 28, 44),
                "specks": [(160, 160, 180)], "face_pattern": "bricks", "shadow": (0.66, 0.66, 0.74),
                "title": (176, 176, 200), "caps": None,
                "floor": ((148, 136, 120), (164, 152, 136), (116, 104, 92)), "floor_pattern": "flags",
                "decals": ["pebble"] * 3 + ["bones"] * 2 + ["skull"]},
    # catacombs (dark rooms: only the torch light shows them)
    "crypt": {"top": (112, 88, 72), "top_hi": (128, 100, 80), "top_lo": (100, 76, 64), "rim": (160, 128, 104),
              "face": (80, 60, 48), "stripe": (56, 40, 32), "stripe_hi": (120, 92, 72),
              "face_foot": (40, 28, 24), "drip": (152, 144, 120), "drip_sh": (112, 104, 88),
              "line": (28, 20, 16),
              "specks": [(152, 136, 112)], "face_pattern": "bricks", "shadow": (0.66, 0.62, 0.62),
              "title": (200, 176, 136), "caps": None,
              "floor": ((96, 72, 56), (112, 84, 64), (76, 56, 44)),
              "decals": ["bones"] * 3 + ["skull"] * 2 + ["pebble"] * 2},
    # purple rooms
    "crystal": {"top": (168, 112, 216), "top_hi": (188, 140, 228), "top_lo": (152, 100, 204),
                "rim": (224, 192, 248),
                "face": (112, 64, 168), "stripe": (80, 40, 136), "stripe_hi": (216, 176, 248),
                "face_foot": (64, 32, 104), "drip": (232, 208, 252), "drip_sh": (192, 160, 232),
                "line": (48, 24, 80), "specks": [(248, 248, 255), (248, 200, 248)], "face_pattern": "facets",
                "shadow": (0.7, 0.62, 0.82), "title": (216, 176, 248), "caps": None,
                "floor": ((72, 56, 104), (92, 76, 124), (56, 40, 88)),
                "decals": ["shard"] * 4 + ["pebble"] * 2},
}
# the secret room ($1E): crystal walls on the 2600's own grey floor, so the author's message - flashing
# through pinks, purples and deep blues like the original - stays readable (it vanished on the dark crystal
# floor)
THEMES["secret"] = {**THEMES["crystal"], "floor": ((164, 164, 172), (180, 180, 188), (148, 148, 156)),
                    "decals": ["shard"]}
# castle interiors: the kingdom's walls, a palace floor
PALACE_FLOORS = {"candy": ((248, 200, 224), (240, 236, 248)), "ice": ((200, 232, 248), (168, 212, 244)),
                 "fire": ((72, 44, 56), (104, 52, 48))}
PALACE_DECALS = {"candy": ["mint"], "ice": ["crystal"], "fire": ["ember"]}
for _kingdom, _floor in PALACE_FLOORS.items():
    THEMES[_kingdom + "_in"] = {**THEMES[_kingdom], "floor": (*_floor, _floor[1]), "floor_pattern": "checker",
                                "caps": None, "decals": PALACE_DECALS[_kingdom]}


def world_hash(xx: Grid, yy: Grid) -> Grid:
    # 64-bit on purpose: the products pass 2^31, and a 32-bit platform (the browser build) would wrap them
    xx, yy = xx.astype(np.int64), yy.astype(np.int64)
    return (xx * 73856093 ^ yy * 19349663) & 0xFFFF


def make_floor(theme: str, size: int = 32) -> Picture:
    """Procedural ground tile for themes without a floor tile: base + scattered light/dark specks."""
    settings = THEMES[theme]
    base, light, dark = (np.array(colour, np.uint8) for colour in settings["floor"])
    yy, xx = np.mgrid[0:size, 0:size]
    hsh = world_hash(xx, yy)
    tile = np.zeros((size, size, 3), np.uint8)
    tile[:] = base
    pattern = settings.get("floor_pattern", "specks")
    if pattern == "checker":  # palace tiles, 8 px, with a soft bevel
        tile[((xx // 8) + (yy // 8)) % 2 == 1] = light
        tile[(xx % 8 == 0) | (yy % 8 == 0)] = (base.astype(int) * 0.9).astype(np.uint8)
    elif pattern == "flags":  # flagstones: 16x8 slabs in running bond, dark joints, speckled
        joint = (yy % 8 == 7) | (((xx + (yy // 8) % 2 * 8) % 16) == 15)
        tile[hsh % 19 == 0] = light
        tile[joint] = dark
    else:
        tile[hsh % 23 == 0] = light
        tile[hsh % 29 == 3] = dark
    return tile


def merlons(walls: Mask, band: int = 16) -> list[tuple[int, int]]:
    """The castle battlements: narrow wall runs (<= 8 px) in the top half-row -> list of (x0, x1)."""
    row = walls[band // 2]
    runs, x = [], 0
    while x < len(row):
        if row[x]:
            x1 = x
            while x1 < len(row) and row[x1]:
                x1 += 1
            if x1 - x <= 8:
                runs.append((x, x1))
            x = x1
        else:
            x += 1
    return runs


def paint_themed_walls(img: Floats, walls: Mask, yy: Grid, xx: Grid, face_h: int, theme: str) -> None:
    """Top with gentle patches + specks and a light rim, side strips a shade darker, a patterned front face
    with drips over its top edge, line art in the theme's dark colour. World space (rooms tile seamlessly)."""
    settings = THEMES[theme]
    colours = {name: np.array(value, float) for name, value in settings.items()
               if isinstance(value, tuple) and len(value) == 3 and name != "shadow"}
    paint_wall_tops(img, walls, colours)
    depth = face_depth(walls, yy, face_h)
    face = depth > 0
    body = walls & ~face
    hsh = world_hash(xx, yy)
    paint_specks(img, body, hsh, settings["specks"])
    paint_sides_and_rim(img, walls, body, yy, xx, colours)
    row = face_h - depth  # 0 = top of the face
    img[face] = colours["face"]
    paint_face_pattern(img, face, row, xx, hsh, settings["face_pattern"], colours)
    img[face & (depth == 1)] = colours["face_foot"]
    drip = paint_drips(img, face, row, xx, colours)
    paint_line_art(img, walls, face, drip, yy, xx, colours["line"])


def paint_wall_tops(img: Floats, walls: Mask, colours: Colours) -> None:
    """The walls' tops: the theme's colour in soft patches, lighter and darker - the same in every room."""
    h, w = walls.shape
    patches_rng = np.random.default_rng(7)
    noise = Image.fromarray((patches_rng.random((h // 32 + 2, w // 32 + 2)) * 255).astype(np.uint8))
    soft = np.array(noise.resize((w + 64, h + 64), Image.Resampling.BICUBIC))[32:32 + h, 32:32 + w] / 255.0
    darker_or_plain = np.where((soft < 0.25)[..., None], colours["top_lo"], colours["top"])
    top = np.where((soft > 0.72)[..., None], colours["top_hi"], darker_or_plain)
    img[walls] = top[walls]


def paint_specks(img: Floats, body: Mask, hsh: Grid, specks: list[Rgb]) -> None:
    """Sprinkles on the tops, 2 px long, across or down."""
    for i, colour in enumerate(specks):
        dot = (hsh % 509 == i * 7) & body
        across = dot & ((hsh >> 8) % 2 == 0)
        img[dot] = colour
        img[np.roll(across, 1, axis=1) & body] = colour
        img[np.roll(dot & ~across, 1, axis=0) & body] = colour


def paint_sides_and_rim(img: Floats, walls: Mask, body: Mask, yy: Grid, xx: Grid, colours: Colours) -> None:
    """3 px strips next to open floor left and right, a shade darker (the wall's side in 3/4 view), and a
    light rim along the top edge."""
    w = walls.shape[1]
    side = np.zeros_like(walls)
    for distance in (1, 2, 3):
        side |= body & (~np.roll(walls, distance, axis=1) | ~np.roll(walls, -distance, axis=1))
    side &= (xx >= 3) & (xx < w - 3)
    img[side] = img[side] * 0.86
    rim = body & ~np.roll(walls, 1, axis=0) | body & ~np.roll(walls, 2, axis=0)
    img[rim & (yy > 1)] = colours["rim"]


def paint_face_pattern(img: Floats, face: Mask, row: Grid, xx: Grid, hsh: Grid, pattern: str,
                       colours: Colours) -> None:
    """The front face's pattern: two colours (stripe, stripe_hi) drawn over the face colour."""
    stripe, stripe_hi = colours["stripe"], colours["stripe_hi"]
    if pattern == "wafer":
        img[face & (xx % 6 == 0)] = stripe
        img[face & (xx % 6 == 1)] = stripe_hi
    elif pattern == "ice_blocks":  # ice bricks + diagonal glints
        joint = (row % 5 == 4) | (((xx + (row // 5) * 6) % 12) == 0)
        img[face & joint] = stripe
        img[face & ~joint & ((xx + row) % 9 == 0)] = stripe_hi
    elif pattern == "cracks":  # dark rock with glowing cracks that zig-zag down
        crack = ((xx + (row // 2) % 2) % 11 == 0) | ((xx - (row // 3) % 2) % 17 == 5)
        img[face & crack] = stripe
        img[face & crack & (row % 3 == 0)] = stripe_hi
    elif pattern == "rock":  # cliff: uneven horizontal strata, the odd vertical crack
        strata = ((row + (xx // 7) % 2) % 4 == 3)
        img[face & strata] = stripe
        img[face & ~strata & ((row + (xx // 7) % 2) % 4 == 0)] = stripe_hi
        img[face & (hsh % 13 == 0) & (row > 3)] = stripe
    elif pattern == "leaves":  # hedge: leaf clumps
        img[face & (hsh % 4 == 0)] = stripe
        img[face & (hsh % 7 == 1)] = stripe_hi
    elif pattern == "bricks":
        joint = (row % 4 == 3) | (((xx + (row // 4) * 4) % 8) == 0)
        img[face & joint] = stripe
        img[face & ~joint & (row % 4 == 0)] = stripe_hi
    elif pattern == "facets":  # crystal: diagonal facets
        img[face & ((xx + row) % 7 == 0)] = stripe
        img[face & ((xx - row) % 7 == 0)] = stripe_hi


def paint_drips(img: Floats, face: Mask, row: Grid, xx: Grid, colours: Colours) -> Mask:
    """Icing / snow / lava / grass running over the face's top edge, in 4 px drips of varied length.
    -> where the drips are."""
    group = (xx // 4).astype(np.int64)   # the hash constant needs 64 bits (see world_hash)
    group_length = np.array([0, 1, 2, 4, 6, 3, 1, 5])[((group * 2654435761) >> 5) % 8]
    drip_edge = (xx % 4 == 0) | (xx % 4 == 3)
    drip_length = 2 + np.where(drip_edge, np.maximum(group_length - 2, 0), group_length)
    drip = face & (row < drip_length)
    img[drip] = colours["drip"]
    img[drip & ((xx % 4 == 3) | (row == drip_length - 1))] = colours["drip_sh"]
    if "drip_core" in colours:
        img[drip & (row == 0)] = colours["drip_core"]
    return drip


def paint_line_art(img: Floats, walls: Mask, face: Mask, drip: Mask, yy: Grid, xx: Grid,
                   line: Floats) -> None:
    """A dark line around the walls, and where the top meets the face (not across the drips)."""
    h, w = walls.shape
    above_below = np.roll(walls, 1, 0) & np.roll(walls, -1, 0)
    either_side = np.roll(walls, 1, 1) & np.roll(walls, -1, 1)
    edge = walls & ~(above_below & either_side)
    edge &= (yy > 0) & (yy < h - 1) & (xx > 0) & (xx < w - 1)
    img[edge] = line
    crease = face & ~np.roll(face, 1, axis=0) & (yy > 0)
    img[crease & ~drip] = line


def caps_sprites(theme: str) -> list[Picture]:
    art, cap_colours = CAPS[theme]
    out = []
    for colour in cap_colours:
        colours = {"C": colour, "h": shade(colour, 1.3), "K": shade(colour, 0.4), "W": (255, 248, 216)}
        out.append(text_art(art, colours))
    return out


def paint_room(room: dict[str, Any], theme: str = "candy", floor_tile: Picture | None = None, seed: int = 0,
               face_h: int = 10) -> Picture:
    """One room in a theme. floor_tile: a ground tile (grass.png); else the theme's procedural floor."""
    settings = THEMES[theme]
    exact = L.wall_mask(room)
    walls = rounded_mask(exact, radius=3)
    if room["thin_wall_left"] or room["thin_wall_right"]:  # 4 px thin walls would melt away when rounded
        walls |= L.wall_mask({**room, "grid": [[0] * len(row) for row in room["grid"]]})
    h, w = walls.shape
    caps = merlons(exact) if settings.get("caps", True) is not None else []
    for x0, x1 in caps:  # keep the battlements' exact shape (rounding melts 6 px merlons into bumps)
        walls[:16, x0:x1] = exact[:16, x0:x1]
    yy, xx = np.mgrid[0:h, 0:w]
    if floor_tile is None:
        floor_tile = make_floor(theme)
    img = floor_tile[yy % floor_tile.shape[0], xx % floor_tile.shape[1]].astype(float)
    rng = np.random.default_rng(seed)
    field = Image.fromarray((rng.random((h // 24 + 2, w // 24 + 2)) * 255).astype(np.uint8))
    field = np.array(field.resize((w + 48, h + 48), Image.Resampling.BICUBIC))[24:24 + h, 24:24 + w] / 255.0
    if settings.get("floor_pattern") != "checker":  # palace tiles stay clean
        img[field > 0.62] *= 1.08 if theme == "ice" else 1.12
        img[field < 0.3] *= 0.94 if theme == "ice" else 0.9
    paint_themed_walls(img, walls, yy, xx, face_h, theme)
    shadow = ~walls & (np.roll(walls, 1, 0) | np.roll(walls, 2, 0) | np.roll(walls, 3, 0)) & (yy > 2)
    img[shadow] *= np.array(settings["shadow"])
    img = snes_rgb(np.clip(img, 0, 255).astype(np.uint8))
    sprites = caps_sprites(theme) if caps else []
    for i, (x0, x1) in enumerate(caps):
        cap = sprites[i % len(sprites)]
        blit(img, cap, (x0 + x1 - cap.shape[1]) // 2, 1)
    scatter_decals(img, walls, settings["decals"], rng)
    return img


def scatter_decals(img: Picture, walls: Mask, names: list[str], rng: np.random.Generator, most: int = 46,
                   tries: int = 600) -> None:
    """Decorations at random places on open ground, clear of walls and of each other."""
    h, w = walls.shape
    wide_walls = Image.fromarray(walls.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(9))
    free = ~np.array(wide_walls).astype(bool)
    placed = 0
    for _ in range(tries):
        if placed >= most:
            break
        picture = decal(names[rng.integers(len(names))])
        picture_h, picture_w = picture.shape[:2]
        y, x = rng.integers(0, h - picture_h), rng.integers(0, w - picture_w)
        if free[y:y + picture_h, x:x + picture_w].all():
            blit(img, picture, x, y)
            free[max(0, y - 6):y + picture_h + 6, max(0, x - 6):x + picture_w + 6] = False
            placed += 1


GATE_THEME = {0x01: "candy", 0x02: "ice", 0x03: "fire"}  # gold / white / black castle
GATE_COLOURS = {  # line, bar, the bar's other colour, crossbar
    "candy": ((104, 32, 72), (248, 248, 248), (232, 56, 72), (248, 200, 224)),
    "ice": ((40, 64, 136), (200, 232, 252), (136, 200, 248), (240, 252, 255)),
    "fire": ((32, 16, 32), (96, 80, 88), (248, 136, 32), (136, 112, 112))}


def gate_sprite(w: int, h: int, theme: str) -> Picture:
    """Themed portcullis at the original's current height: candy-stripe bars / icicle bars / glowing iron."""
    out = np.zeros((h, w, 4), np.uint8)
    line, bar, bar2, cross = GATE_COLOURS[theme]
    out[:, :] = (*line, 255)
    for x in range(1, w - 1, 3):
        for y in range(h):
            if theme == "candy":
                colour = bar2 if (y + x) % 6 < 3 else bar  # diagonal stripes
            elif theme == "ice":
                colour = bar if y % 5 else bar2
            else:
                colour = bar2 if y >= h - 4 else bar  # iron bars glowing at the tips
            out[y, x] = (*colour, 255)
    for y in range(2, h, 6):
        out[y, 1:w - 1] = (*cross, 255)
    if h >= 4:
        out[h - 2:, :] = 0
        for x in range(1, w - 1, 3):
            out[h - 2:, x] = (*(bar2 if theme != "ice" else bar), 255)
    return out
