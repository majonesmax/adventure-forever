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

import numpy as np
from PIL import Image, ImageFilter

from shared import layout as L
from shared.pixelart import blit, shade, snes_rgb

K_ = (32, 32, 48)
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
.Y.Y.""", {"K": K_, "W": (248, 248, 248), "Y": (248, 152, 32)}),
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
.dd.""", {"L": (140, 108, 80), "l": (176, 140, 104), "d": (92, 68, 52)}),  # brown: the only grey speck is the dot
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

def decal(name):
    art, cols = DECALS[name]
    rows = art.strip("\n").split("\n")
    im = np.zeros((len(rows), len(rows[0]), 4), np.uint8)
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch != ".":
                im[y, x] = (*cols[ch], 255)
    return im


def rounded_mask(m, radius=4):
    """Round the corners of a wall mask: blur, re-threshold. Edges replicate so walls touching the screen
    edge stay straight there."""
    p = radius * 3
    big = np.pad(m.astype(np.uint8) * 255, p, mode="edge")
    soft = np.array(Image.fromarray(big).filter(ImageFilter.GaussianBlur(radius)))[p:-p, p:-p]
    return soft >= 115  # a touch under half: 1-column (6 px) maze walls keep their full width


def face_depth(m, yy, face_h):
    """For wall pixels: how far down to open floor (1..face_h), 0 elsewhere = the front-face band."""
    h = m.shape[0]
    depth = np.zeros(m.shape, int)
    for d in range(face_h, 0, -1):
        depth[m & ~np.roll(m, -d, axis=0) & (yy < h - d)] = d
    return depth


# Wall themes. drip = what runs over the face top (icing / snow / lava); face pattern per theme.
THEMES = {
    "candy": {"top": (240, 160, 200), "top_hi": (248, 176, 216), "top_lo": (232, 148, 192), "rim": (252, 216, 236),
              "face": (200, 96, 152), "stripe": (168, 72, 128), "stripe_hi": (224, 128, 176),
              "face_foot": (136, 48, 104), "drip": (248, 240, 248), "drip_sh": (216, 200, 232), "line": (104, 32, 72),
              "specks": [(248, 248, 248), (248, 224, 64), (96, 208, 240), (232, 56, 72), (120, 216, 96)],
              "face_pattern": "wafer", "shadow": (0.72, 0.68, 0.82), "title": (236, 174, 212),
              "decals": ["tuft"] * 6 + ["flower"] * 2 + ["flower2"] * 2 + ["mint", "rock"]},
    "ice": {"top": (144, 196, 240), "top_hi": (168, 212, 244), "top_lo": (128, 184, 232), "rim": (216, 240, 252),
            "face": (104, 168, 224), "stripe": (72, 128, 200), "stripe_hi": (176, 224, 248),
            "face_foot": (56, 96, 168), "drip": (248, 252, 255), "drip_sh": (208, 224, 240), "line": (40, 64, 136),
            "specks": [(255, 255, 255), (152, 208, 248)], "face_pattern": "ice_blocks",
            "shadow": (0.8, 0.86, 0.96), "title": (168, 216, 248),
            "floor": ((236, 244, 252), (216, 232, 248), (196, 220, 244)),
            "decals": ["mound"] * 6 + ["crystal"] * 4 + ["penguin"] + ["ice_rock"]},
    "fire": {"top": (88, 56, 72), "top_hi": (104, 64, 80), "top_lo": (76, 48, 64), "rim": (136, 88, 96),
             "face": (64, 40, 56), "stripe": (232, 96, 32), "stripe_hi": (248, 176, 56),
             "face_foot": (40, 24, 40), "drip": (248, 136, 32), "drip_sh": (216, 72, 24), "line": (32, 16, 32),
             "drip_core": (248, 216, 72), "specks": [(248, 152, 40), (248, 216, 72)], "face_pattern": "cracks",
             "shadow": (0.7, 0.58, 0.58), "title": (248, 152, 56),
             "floor": ((128, 68, 48), (148, 80, 52), (104, 56, 44)),
             "decals": ["ember"] * 4 + ["flame"] * 2 + ["char_rock"] * 3 + ["dead_tuft"] * 3},
    # green rooms outside: grassy cliffs like the DS overworld (grass on top, brown rock face, grass overhang)
    "grass": {"top": (120, 208, 80), "top_hi": (136, 216, 96), "top_lo": (104, 192, 72), "rim": (176, 232, 120),
              "face": (160, 112, 72), "stripe": (120, 80, 48), "stripe_hi": (192, 144, 96),
              "face_foot": (88, 56, 40), "drip": (104, 192, 72), "drip_sh": (64, 144, 48), "line": (48, 72, 32),
              "specks": [(248, 248, 248), (248, 224, 64)], "face_pattern": "rock",
              "shadow": (0.74, 0.8, 0.7), "title": (136, 216, 96), "caps": None,
              "decals": ["tuft"] * 6 + ["flower"] * 2 + ["flower2"] * 2 + ["rock"] * 2},
    # blue labyrinth: a hedge maze in the woods, dirt paths
    "forest": {"top": (48, 120, 64), "top_hi": (64, 144, 72), "top_lo": (40, 104, 56), "rim": (96, 176, 88),
               "face": (32, 88, 48), "stripe": (24, 60, 32), "stripe_hi": (64, 128, 64),
               "face_foot": (16, 40, 24), "drip": (64, 144, 72), "drip_sh": (40, 104, 48), "line": (16, 40, 24),
               "specks": [(232, 72, 72), (248, 248, 248)], "face_pattern": "leaves",
               "shadow": (0.7, 0.72, 0.66), "title": (120, 208, 96), "caps": None,
               "floor": ((200, 168, 112), (216, 188, 132), (176, 144, 96)),
               "decals": ["tuft"] * 3 + ["mushroom"] * 2 + ["rock"] * 2 + ["flower2"]},
    # red maze + top entry room 2: an old stone dungeon with moss
    "dungeon": {"top": (120, 120, 140), "top_hi": (136, 136, 156), "top_lo": (108, 108, 128), "rim": (168, 168, 188),
                "face": (88, 88, 108), "stripe": (60, 60, 80), "stripe_hi": (124, 124, 144),
                "face_foot": (44, 44, 60), "drip": (96, 160, 72), "drip_sh": (64, 120, 56), "line": (28, 28, 44),
                "specks": [(160, 160, 180)], "face_pattern": "bricks", "shadow": (0.66, 0.66, 0.74),
                "title": (176, 176, 200), "caps": None,
                "floor": ((148, 136, 120), (164, 152, 136), (116, 104, 92)), "floor_pattern": "flags",
                "decals": ["pebble"] * 3 + ["bones"] * 2 + ["skull"]},
    # catacombs (dark rooms: only the torch light shows them)
    "crypt": {"top": (112, 88, 72), "top_hi": (128, 100, 80), "top_lo": (100, 76, 64), "rim": (160, 128, 104),
              "face": (80, 60, 48), "stripe": (56, 40, 32), "stripe_hi": (120, 92, 72),
              "face_foot": (40, 28, 24), "drip": (152, 144, 120), "drip_sh": (112, 104, 88), "line": (28, 20, 16),
              "specks": [(152, 136, 112)], "face_pattern": "bricks", "shadow": (0.66, 0.62, 0.62),
              "title": (200, 176, 136), "caps": None,
              "floor": ((96, 72, 56), (112, 84, 64), (76, 56, 44)),
              "decals": ["bones"] * 3 + ["skull"] * 2 + ["pebble"] * 2},
    # purple rooms
    "crystal": {"top": (168, 112, 216), "top_hi": (188, 140, 228), "top_lo": (152, 100, 204), "rim": (224, 192, 248),
                "face": (112, 64, 168), "stripe": (80, 40, 136), "stripe_hi": (216, 176, 248),
                "face_foot": (64, 32, 104), "drip": (232, 208, 252), "drip_sh": (192, 160, 232),
                "line": (48, 24, 80), "specks": [(248, 248, 255), (248, 200, 248)], "face_pattern": "facets",
                "shadow": (0.7, 0.62, 0.82), "title": (216, 176, 248), "caps": None,
                "floor": ((72, 56, 104), (92, 76, 124), (56, 40, 88)),
                "decals": ["shard"] * 4 + ["pebble"] * 2},
}
# the secret room ($1E): crystal walls on the 2600's own grey floor, so the author's message - flashing through
# pinks, purples and deep blues like the original - stays readable (it vanished on the dark crystal floor)
THEMES["secret"] = {**THEMES["crystal"], "floor": ((164, 164, 172), (180, 180, 188), (148, 148, 156)),
                    "decals": ["shard"]}
# castle interiors: the kingdom's walls, a palace floor
for _k, _floor in (("candy", ((248, 200, 224), (240, 236, 248))), ("ice", ((200, 232, 248), (168, 212, 244))),
                   ("fire", ((72, 44, 56), (104, 52, 48)))):
    THEMES[_k + "_in"] = {**THEMES[_k], "floor": (*_floor, _floor[1]), "floor_pattern": "checker", "caps": None,
                          "decals": {"candy": ["mint"], "ice": ["crystal"], "fire": ["ember"]}[_k]}


def world_hash(xx, yy):
    return (xx * 73856093 ^ yy * 19349663) & 0xFFFF


def make_floor(theme, size=32):
    """Procedural ground tile for themes without a floor tile: base + scattered light/dark specks."""
    T = THEMES[theme]
    base, light, dark = (np.array(c, np.uint8) for c in T["floor"])
    yy, xx = np.mgrid[0:size, 0:size]
    hsh = world_hash(xx, yy)
    t = np.zeros((size, size, 3), np.uint8)
    t[:] = base
    pattern = T.get("floor_pattern", "specks")
    if pattern == "checker":  # palace tiles, 8 px, with a soft bevel
        t[((xx // 8) + (yy // 8)) % 2 == 1] = light
        t[(xx % 8 == 0) | (yy % 8 == 0)] = (base.astype(int) * 0.9).astype(np.uint8)
    elif pattern == "flags":  # flagstones: 16x8 slabs in running bond, dark joints, speckled
        joint = (yy % 8 == 7) | (((xx + (yy // 8) % 2 * 8) % 16) == 15)
        t[hsh % 19 == 0] = light
        t[joint] = dark
    else:
        t[hsh % 23 == 0] = light
        t[hsh % 29 == 3] = dark
    return t


def merlons(m0, band=16):
    """The castle battlements: narrow wall runs (<= 8 px) in the top half-row -> list of (x0, x1)."""
    row = m0[band // 2]
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


def paint_themed_walls(img, m, yy, xx, face_h, theme):
    """Top with gentle patches + specks and a light rim, side strips a shade darker, a patterned front face
    with drips over its top edge, line art in the theme's dark colour. World space (rooms tile seamlessly)."""
    T = THEMES[theme]
    h, w = m.shape
    C = {k: np.array(v, float) for k, v in T.items() if isinstance(v, tuple) and len(v) == 3 and k != "shadow"}
    wrng = np.random.default_rng(7)  # fixed: the same top in every room
    soft = Image.fromarray((wrng.random((h // 32 + 2, w // 32 + 2)) * 255).astype(np.uint8))
    soft = np.array(soft.resize((w + 64, h + 64), Image.BICUBIC))[32:32 + h, 32:32 + w] / 255.0
    top = np.where((soft > 0.72)[..., None], C["top_hi"], np.where((soft < 0.25)[..., None], C["top_lo"], C["top"]))
    img[m] = top[m]
    depth = face_depth(m, yy, face_h)
    face = depth > 0
    body = m & ~face
    hsh = world_hash(xx, yy)
    for i, col in enumerate(T["specks"]):
        dot = (hsh % 509 == i * 7) & body
        horiz = dot & ((hsh >> 8) % 2 == 0)
        img[dot] = col
        img[np.roll(horiz, 1, axis=1) & body] = col
        img[np.roll(dot & ~horiz, 1, axis=0) & body] = col
    # sides: 3 px strips next to open floor left/right, a shade darker (the wall's side in 3/4 view)
    side = np.zeros_like(m)
    for d in (1, 2, 3):
        side |= body & (~np.roll(m, d, axis=1) | ~np.roll(m, -d, axis=1))
    side &= (xx >= 3) & (xx < w - 3)
    img[side] = img[side] * 0.86
    rim = body & ~np.roll(m, 1, axis=0) | body & ~np.roll(m, 2, axis=0)
    img[rim & (yy > 1)] = C["rim"]
    # face pattern
    row = face_h - depth  # 0 = top of the face
    img[face] = C["face"]
    if T["face_pattern"] == "wafer":
        img[face & (xx % 6 == 0)] = C["stripe"]
        img[face & (xx % 6 == 1)] = C["stripe_hi"]
    elif T["face_pattern"] == "ice_blocks":  # ice bricks + diagonal glints
        joint = (row % 5 == 4) | (((xx + (row // 5) * 6) % 12) == 0)
        img[face & joint] = C["stripe"]
        img[face & ~joint & ((xx + row) % 9 == 0)] = C["stripe_hi"]
    elif T["face_pattern"] == "cracks":  # dark rock with glowing cracks that zig-zag down
        crack = ((xx + (row // 2) % 2) % 11 == 0) | ((xx - (row // 3) % 2) % 17 == 5)
        img[face & crack] = C["stripe"]
        img[face & crack & (row % 3 == 0)] = C["stripe_hi"]
    elif T["face_pattern"] == "rock":  # cliff: uneven horizontal strata, the odd vertical crack
        strata = ((row + (xx // 7) % 2) % 4 == 3)
        img[face & strata] = C["stripe"]
        img[face & ~strata & ((row + (xx // 7) % 2) % 4 == 0)] = C["stripe_hi"]
        img[face & (hsh % 13 == 0) & (row > 3)] = C["stripe"]
    elif T["face_pattern"] == "leaves":  # hedge: leaf clumps
        img[face & (hsh % 4 == 0)] = C["stripe"]
        img[face & (hsh % 7 == 1)] = C["stripe_hi"]
    elif T["face_pattern"] == "bricks":
        joint = (row % 4 == 3) | (((xx + (row // 4) * 4) % 8) == 0)
        img[face & joint] = C["stripe"]
        img[face & ~joint & (row % 4 == 0)] = C["stripe_hi"]
    elif T["face_pattern"] == "facets":  # crystal: diagonal facets
        img[face & ((xx + row) % 7 == 0)] = C["stripe"]
        img[face & ((xx - row) % 7 == 0)] = C["stripe_hi"]
    img[face & (depth == 1)] = C["face_foot"]
    # drips over the face top
    grp = xx // 4
    glen = np.array([0, 1, 2, 4, 6, 3, 1, 5])[((grp * 2654435761) >> 5) % 8]
    edge_col = (xx % 4 == 0) | (xx % 4 == 3)
    drip_len = 2 + np.where(edge_col, np.maximum(glen - 2, 0), glen)
    drip = face & (row < drip_len)
    img[drip] = C["drip"]
    img[drip & ((xx % 4 == 3) | (row == drip_len - 1))] = C["drip_sh"]
    if "drip_core" in C:
        img[drip & (row == 0)] = C["drip_core"]
    # line art
    edge = m & ~(np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1))
    edge &= (yy > 0) & (yy < h - 1) & (xx > 0) & (xx < w - 1)
    img[edge] = C["line"]
    crease = face & ~np.roll(face, 1, axis=0) & (yy > 0)
    img[crease & ~drip] = C["line"]


def caps_sprites(theme):
    art, colours = CAPS[theme]
    out = []
    for c in colours:
        cols = {"C": c, "h": shade(c, 1.3), "K": shade(c, 0.4), "W": (255, 248, 216)}
        rows = art.strip("\n").split("\n")
        im = np.zeros((len(rows), len(rows[0]), 4), np.uint8)
        for y, r in enumerate(rows):
            for x, ch in enumerate(r):
                if ch != ".":
                    im[y, x] = (*cols[ch], 255)
        out.append(im)
    return out


def paint_room(room, theme="candy", floor_tile=None, seed=0, face_h=10):
    """One room in a theme. floor_tile: a ground tile (grass.png); else the theme's procedural floor."""
    T = THEMES[theme]
    m0 = L.wall_mask(room)
    m = rounded_mask(m0, radius=3)
    if room["thin_wall_left"] or room["thin_wall_right"]:  # 4 px thin walls would melt away when rounded
        m |= L.wall_mask({**room, "grid": [[0] * len(r) for r in room["grid"]]})
    h, w = m.shape
    caps = merlons(m0) if T.get("caps", True) is not None else []
    for x0, x1 in caps:  # keep the battlements' exact shape (rounding melts 6 px merlons into bumps)
        m[:16, x0:x1] = m0[:16, x0:x1]
    yy, xx = np.mgrid[0:h, 0:w]
    if floor_tile is None:
        floor_tile = make_floor(theme)
    img = floor_tile[yy % floor_tile.shape[0], xx % floor_tile.shape[1]].astype(float)
    rng = np.random.default_rng(seed)
    field = Image.fromarray((rng.random((h // 24 + 2, w // 24 + 2)) * 255).astype(np.uint8))
    field = np.array(field.resize((w + 48, h + 48), Image.BICUBIC))[24:24 + h, 24:24 + w] / 255.0
    if T.get("floor_pattern") != "checker":  # palace tiles stay clean
        img[field > 0.62] *= 1.08 if theme == "ice" else 1.12
        img[field < 0.3] *= 0.94 if theme == "ice" else 0.9
    paint_themed_walls(img, m, yy, xx, face_h, theme)
    sh = ~m & (np.roll(m, 1, 0) | np.roll(m, 2, 0) | np.roll(m, 3, 0)) & (yy > 2)
    img[sh] *= np.array(T["shadow"])
    img = snes_rgb(np.clip(img, 0, 255).astype(np.uint8))
    sprites = caps_sprites(theme) if caps else []
    for i, (x0, x1) in enumerate(caps):
        c = sprites[i % len(sprites)]
        blit(img, c, (x0 + x1 - c.shape[1]) // 2, 1)
    free = ~np.array(Image.fromarray(m.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(9))).astype(bool)
    placed = 0
    for _ in range(600):
        if placed >= 46:
            break
        d = decal(T["decals"][rng.integers(len(T["decals"]))])
        dh, dw = d.shape[:2]
        y, x = rng.integers(0, h - dh), rng.integers(0, w - dw)
        if free[y:y + dh, x:x + dw].all():
            blit(img, d, x, y)
            free[max(0, y - 6):y + dh + 6, max(0, x - 6):x + dw + 6] = False
            placed += 1
    return img


GATE_THEME = {0x01: "candy", 0x02: "ice", 0x03: "fire"}  # gold / white / black castle


def gate_sprite(w, h, theme):
    """Themed portcullis at the original's current height: candy-stripe bars / icicle bars / glowing iron."""
    out = np.zeros((h, w, 4), np.uint8)
    line, bar, bar2, cross = {"candy": ((104, 32, 72), (248, 248, 248), (232, 56, 72), (248, 200, 224)),
                              "ice": ((40, 64, 136), (200, 232, 252), (136, 200, 248), (240, 252, 255)),
                              "fire": ((32, 16, 32), (96, 80, 88), (248, 136, 32), (136, 112, 112))}[theme]
    out[:, :] = (*line, 255)
    for x in range(1, w - 1, 3):
        for y in range(h):
            if theme == "candy":
                c = bar2 if (y + x) % 6 < 3 else bar  # diagonal stripes
            elif theme == "ice":
                c = bar if y % 5 else bar2
            else:
                c = bar2 if y >= h - 4 else bar  # iron bars glowing at the tips
            out[y, x] = (*c, 255)
    for y in range(2, h, 6):
        out[y, 1:w - 1] = (*cross, 255)
    if h >= 4:
        out[h - 2:, :] = 0
        for x in range(1, w - 1, 3):
            out[h - 2:, x] = (*(bar2 if theme != "ice" else bar), 255)
    return out
