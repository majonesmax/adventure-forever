"""The pbj pack's text art - Adventure Forever's own cast, original characters, no outside IP.

  PBJ (hero)            a kid in a tan bear-ear hat, maroon sweatshirt, blue jeans - 16x26, 4 views x 2 frames
  Alice (bridge)        a big Scottish terrier stretched as a long-dog bridge (black, or brown)
  The Yeti   (red dragon)     shaggy white fur, pale blue face, horns, red scarf
  The Chicken (yellow dragon) a giant white hen - the coward of the three
  The Bog    (green dragon)   a swamp monster with glowing eyes and weedy hair
  Magpie     (the bat)        steals shiny things
  The Storybook (the chalice), keys, sword, magnet, gates.
Colours are SNES 15-bit (multiples of 8); every sprite stays within 15 colours.

Usage: python packs/pbj/source/pbj_sprites.py   -> packs/pbj/cast/*.png + shots/snes/cast.png
"""

import os
import sys

import numpy as np
from PIL import Image

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
sys.path.insert(0, REPO_ROOT)
from engine import paths
from content.cast import ITEMS
from content.pictures import save_folder
from shared import pixelart as PX
from shared.pixelart import edited, mirrored


def from_ascii(art, colours):
    """Strict: a character without a colour is an error (catches typos in the hand-drawn art)."""
    return PX.from_ascii(art, colours, strict=True)


# ---- PBJ ----
PBJ_COLOURS = {"K": (40, 24, 24), "H": (200, 152, 96), "h": (160, 112, 64), "E": (232, 192, 152),
               "R": (112, 64, 40), "S": (200, 152, 104), "X": (184, 64, 72), "M": (136, 32, 48),
               "m": (96, 24, 40), "J": (72, 104, 184), "j": (48, 72, 136), "W": (240, 240, 240)}
_PBJ_HAT = """
..KK........KK..
.KHHK......KHHK.
.KHEHKKKKKKHEHK.
.KHHHHHHHHHHHhK.
KHHHHHHHHHHHHHhK
KhhhhhhhhhhhhhhK"""
_PBJ_FACE = """
KRRSSSSSSSSSSRRK
KRSSKSSSSSSKSSRK
KRSSKSSSSSSKSSRK
KRSSSSSSSSSSSSRK
.KRSSSSXXSSSSRK.
..KKSSSSSSSSKK.."""
_PBJ_HAIR_BACK = """
KRRRRRRRRRRRRRRK
KRRRRRRRRRRRRRRK
KRRRRRRRRRRRRRRK
KRRRRRRRRRRRRRRK
.KRRRRRRRRRRRRK.
..KKRRRRRRRRKK.."""
_PBJ_BODY = """
..KMMMMMMMMMMK..
.KMMMMMMMMMMMmK.
KMMKMMMMMMMmKMmK
KMMKMMMMMMMmKMmK
KMMKMMMMMMMmKMmK
KSSKmmmmmmmmKSSK
.KKKJJJJJJJJKKK.
...KJJJJJJJjK...
...KJJJKKJJjK..."""
_PBJ_LEGS = ["""
...KJJK..KJjK...
...KJJK..KJjK...
...KWWK..KWWK...
..KKKKK..KKKKK..
................""", """
...KJJK..KJjK...
...KWWK..KJjK...
..KKKKK..KWWK...
.........KKKKK..
................"""]
_PBJ_SIDE = """
................
....KK....KK....
...KHHK..KHHK...
...KHHHKKHHHHK..
..KHHHHHHHHHHHK.
.KHHHHHHHHHHHHHK
.KhhhhhhhhhhhhhK
.KRRRRRSSSSSSSK.
.KRRRRSSSSSKSSK.
.KRRRRSSSSSKSSK.
.KRRRRSSSSSSSSSK
..KRRRSSSSSXSK..
...KKKSSSSSKK...
....KMMMMMMK....
...KMMMMMMMmK...
...KMMMMMMMmK...
...KMMMMMMMmK...
...KMMMMMSSmK...
...KmmmmmmmmK...
....KJJJJJJK....
....KJJJJJjK...."""
_PBJ_SIDE_LEGS = ["""
....KJJK.KJjK...
....KJJK.KJjK...
....KJJK.KJjK...
....KWWWKKWWWK..
................""", """
...KJJK...KJjK..
..KJJK.....KJjK.
..KJJK.....KJjK.
.KWWWK.....KWWWK
................"""]


def pbj_frames():
    """view -> [stand, stride] RGBA 16x26 (left = mirrored right)."""
    colours = PBJ_COLOURS
    front = [from_ascii(_PBJ_HAT + _PBJ_FACE + _PBJ_BODY + legs, colours) for legs in _PBJ_LEGS]
    back_hat = _PBJ_HAT.replace("E", "H")  # no inner ears from behind
    back_body = back_hat + _PBJ_HAIR_BACK + _PBJ_BODY.replace("S", "M")
    back = [from_ascii(back_body + legs, colours) for legs in _PBJ_LEGS]
    side = [from_ascii(_PBJ_SIDE + legs, colours) for legs in _PBJ_SIDE_LEGS]
    return {"down": front, "up": back, "right": side, "left": [frame[:, ::-1] for frame in side]}


# ---- Alice, the Scottie long-dog bridge ----
ALICE_COLOURS = {
    "black": {"K": (16, 16, 24), "B": (56, 56, 68), "h": (104, 104, 120), "W": (248, 248, 248),
              "R": (208, 40, 56)},
    "brown": {"K": (48, 28, 16), "B": (128, 84, 52), "h": (176, 128, 88), "W": (248, 248, 248),
              "R": (208, 40, 56)},
}
_ALICE_HEAD = mirrored("""
.KK.........
.KBK........
.KBBK.......
.KBBBKKKKKKK
.KBBBBBBBBBB
.KBBBBBBBBBB
.KBhhhhBBBBB
.KBBhhhhBBBB
.KBBKWKBBBBB
.KBBKKKBBBBB
.KBBBBBBBBBB
..KBBBBBhhhh
..KBBBBhhhhh
..KBBBhhhhhh
..KBBBhhhKKK
..KBBBhhhhKK
...KBBhhhhhh
...KBhhhhhhh
....KhhhhhBh
....KhKhhKhh
..KRRRRRRRRR""")
_ALICE_FRONT_LEGS = mirrored("""
..KBBBBBBBBB
KBBKBBBBBBBB
KBBK.KBBBBBB
.KK..KBBBBBB""")
_ALICE_STRETCH = mirrored("""
.....KBhBBhB""")
_ALICE_TAIL = mirrored("""
.....KBBBBBB
....KBBBBBBB
KBBKBBBBBBBB
KBBK.KBBBBBB
.KK...KBBBBB
.......KBBBB
........KKBK
.........KBK
.........KK.""")


def alice_bridge(height, width=None, coat="black"):
    """Alice stretched to `height`: head, front legs, a long wiry back, hind legs and tail (24 wide)."""
    colours = ALICE_COLOURS[coat]
    parts = (_ALICE_HEAD, _ALICE_FRONT_LEGS, _ALICE_STRETCH, _ALICE_TAIL)
    head, front, mid, tail = (from_ascii(art, colours) for art in parts)
    back_rows = max(1, height - head.shape[0] - front.shape[0] - tail.shape[0])  # her back stretches
    out = np.concatenate([head, front, np.repeat(mid, back_rows, axis=0), tail])
    if width and width > out.shape[1]:
        pad = width - out.shape[1]
        out = np.pad(out, ((0, 0), (pad // 2, pad - pad // 2), (0, 0)))
    return out


def alice_portrait(coat="black"):
    """Head + collar only (the win message, the title screen)."""
    return from_ascii(_ALICE_HEAD, ALICE_COLOURS[coat])


# ---- villains: normal / roar / dead (= normal upside down, like the 2600) ----
YETI_COLOURS = {"K": (24, 32, 56), "F": (240, 244, 252), "f": (192, 204, 228), "B": (152, 196, 232),
                "b": (112, 160, 208), "H": (232, 216, 176), "T": (255, 255, 255), "M": (72, 24, 48),
                "S": (208, 56, 64), "s": (152, 32, 48)}
YETI = mirrored("""
.............
.......KK....
......KHHK...
......KHHKKKK
.....KFFFFFFF
....KFFFFFFFF
....KFFFBBBBB
....KFFBBKBBB
....KFFBBKBBB
....KFFBBBBBB
....KFFBBBKKK
....KFFBBBBTT
....KFFFBBBBB
...KSSSSSSSSS
..KFFKSSSSSSS
.KFFFFKFFFSSS
.KFFFFKFFFSSS
.KFFFFKFFFFFF
.KFFFFKFFFFFF
.KfFFFKFFFFFF
.KffffKFFFFFF
KBBBBKKFFFFFF
KBKBKBKFFFFFF
.......KFFFFF
.......KFFFFF
.......KFFFFF
......KFFFFFF
......KFFFFKK
......KFFFK..
.....KFFFFK..
.....KKKKKK..
.............""", shade={"F": "f", "B": "b"})
YETI_ROAR = edited(YETI, {10: [(7, "BBKKKKKKKKBB")], 11: [(7, "BKMMMMMMMMKB")], 12: [(7, "BBKTKTTKTKBB")],
                        14: [(0, ".."), (24, "..")], 15: [(0, "."), (25, ".")],
                        21: [(0, "....."), (21, ".....")], 22: [(0, "......."), (19, ".......")],
                        3: [(0, "KBKBK"), (21, "KBKBK")], 4: [(0, "KBBBBK"), (20, "KBBBBK")],
                        5: [(1, "KFFK"), (21, "KFFK")], 6: [(1, "KFFK"), (21, "KFFK")],
                        7: [(1, "KFFK"), (21, "KFFK")], 8: [(2, "KFK"), (21, "KFK")],
                        9: [(2, "KFK"), (21, "KFK")]})

CHICKEN_COLOURS = {"K": (56, 40, 32), "Y": (248, 244, 232), "y": (200, 192, 176), "O": (248, 168, 40),
                   "R": (216, 40, 48), "W": (255, 255, 255), "M": (96, 24, 16)}
CHICKEN = mirrored("""
.............
........KK.KK
.......KRRKRR
.......KRRRRR
......KYYYYYY
.....KYYYYYYY
.....KYWWKYYY
.....KYWKKYYY
.....KYYYYYOO
......KYYYOOO
......KYYYRRO
.......KYYYRR
.....KKYYYYYY
...KKYYYYYYYY
..KYYYKYYYYYY
.KYYYYYKYYYYY
.KYYYYYYKYYYY
KYYYYYYYKYYYY
KYYYYYYKYYYYY
KyYYYYKYYYYYY
.KyyyKYYYYYYY
..KKKYYYYYYYY
....KYYYYYYYY
.....KKYYYYYY
.......KKKKKK
.........KOK.
.........KOK.
........KOOOK
........KKKKK""", shade={"Y": "y"})
# roar: beak wide open, wings flung up
CHICKEN_ROAR = edited(CHICKEN, {8: [(11, "KOOK")], 9: [(10, "KMMMMK")],
                              10: [(1, "K"), (10, "KOMMOK"), (24, "K")],
                              11: [(0, "KYK"), (10, "KKOOKK"), (23, "KYK")],
                              12: [(0, "KYK"), (23, "KYK")], 13: [(0, ".KK"), (23, "KK.")],
                              17: [(0, "."), (25, ".")], 18: [(0, "."), (25, ".")]})


BOG_COLOURS = {"K": (16, 32, 24), "G": (72, 152, 72), "g": (48, 112, 56), "L": (120, 200, 96),
               "E": (232, 248, 120), "W": (40, 88, 40), "T": (232, 232, 200), "M": (40, 16, 24)}
BOG = mirrored("""
.............
.....K..K..K.
....KWK.KWKWK
....KWKKKWKWK
...KWWKGGGKGG
...KWGGGGGGGG
..KWGGGGGGGGG
..KWGGKKKGGGG
..KWGGKEKGGGG
..KWGGKKKGGGG
..KWGGGGGGGGG
..KWGGGGGKKKK
..KWGGGGKTKTK
..KWGGGGGGGGG
.KWGGGGGGGGGG
.KWLGGGGGGGGG
KWLLKGGGGGGGG
KWLLKGGGGGGGG
KWLLKGGGLGGGG
KLLLKGGGGGGGG
KLKLKGGGGGGGG
.K.K.KGGGGLGG
.....KGGGGGGG
.....KGGGGGGG
....KGGGGGGGG
....KGGKGGKGG
...KGGK.KGK.K
...KKK..KKK..
.............""", shade={"G": "g"})
BOG_ROAR = edited(BOG, {11: [(7, "GKKKKKKKKKKG")], 12: [(7, "KTMMMMMMMMTK")], 13: [(7, "KTKTKMMKTKTK")],
                      8: [(7, "KEE"), (16, "EEK")]})

MAGPIE_COLOURS = {"K": (16, 16, 24), "B": (40, 40, 56), "W": (248, 248, 248), "U": (64, 112, 200),
                  "u": (40, 72, 152), "E": (232, 56, 56), "Y": (120, 120, 136)}
MAGPIE_UP = mirrored("""
K..........
KUK........
KUUK.......
KUUUK......
.KUUUK..KKK
..KUUUKKBBB
...KUuKBBEB
....KKBBBBB
.....KBBBWW
.....KBWWWW
......KWWWW
......KKBBB
.......KBKK
.......KK..
...........""")
MAGPIE_DOWN = edited(MAGPIE_UP, {0: [(0, "...."), (18, "....")], 1: [(0, "...."), (18, "....")],
                               2: [(0, "...."), (18, "....")], 3: [(0, "....."), (17, ".....")],
                               4: [(0, "......"), (16, "......")], 5: [(0, "......"), (16, "......")],
                               7: [(0, "KKKK"), (18, "KKKK")], 8: [(0, "KUUUKK"), (16, "KKUUUK")],
                               9: [(1, "KUuK"), (17, "KuUK")], 10: [(2, "KK"), (18, "KK")]})

# ---- items ----
BOOK = """
KKKKKKKKKKKKK..
KUUUUUUUUUUUKK.
KUuUUUYUUUuUKPK
KUUUUYYYUUUUKPK
KUUUYYYYYUUUKPK
KUYYYYYYYYYUKPK
KUUYYYYYYYUUKPK
KUUUYYYYYUUUKPK
KUUYYKUKYYUUKPK
KUUYKUUUKYUUKPK
KUUUUUUUUUUUKPK
KUuUUUUUUUuUKPK
KUUUUUUUUUUUKPK
KKKKKKKKKKKKKPK
.KPPPPPPPPPPPPK
..KKKKKKKKKKKKK"""
BOOK_COLOURS = {"K": (16, 24, 56), "U": (56, 96, 192), "u": (232, 200, 64), "Y": (248, 216, 72),
                "P": (240, 232, 208)}
SWORD = """
...........KK....
.KKKKKKKKKKYYK.K.
KWWWWWWWWWKYYKKRK
KwwwwwwwwwKYYKRYK
.KKKKKKKKKKYYK.K.
...........KK...."""
SWORD_COLOURS = {"K": (40, 24, 16), "W": (248, 248, 248), "w": (176, 184, 200), "Y": (248, 200, 40),
                 "R": (56, 120, 216)}
KEY = """
...........KKKK.
..........KCCCCK
.KKKKKKKKKKChhCK
KCCCCCCCCCCCKKCK
KCKCKKKKKKKCKKCK
KCKCK.....KCCCCK
KKKKK......KKKK."""
KEY_COLOURS = {0x0B: {"C": (248, 136, 200), "h": (248, 224, 72)},  # gold key -> Gumdrop Hills
               0x0C: {"C": (136, 208, 248), "h": (240, 252, 255)},  # white key -> Frosthold
               0x0D: {"C": (232, 88, 32), "h": (248, 216, 72)}}     # black key -> Ember Keep
MAGNET = """
....KKKKKKKK....
...KRRRRRRRRK...
..KRRWRRRRRRRK..
..KRRKKKKKKRRK..
..KRRK....KRRK..
..KRRK....KRRK..
..KRRK....KRRK..
..KSSK....KSSK..
..KSSK....KSSK..
..KKKK....KKKK.."""
MAGNET_COLOURS = {"K": (40, 16, 24), "R": (224, 56, 64), "W": (248, 200, 200), "S": (200, 208, 216)}


def villain_frames():
    """(pose, 2600 dragon colour) -> RGBA: red = the Yeti, yellow = the giant chicken (the coward), green =
    the Bog."""
    villains = {"red": (YETI, YETI_ROAR, YETI_COLOURS), "yellow": (CHICKEN, CHICKEN_ROAR, CHICKEN_COLOURS),
                "green": (BOG, BOG_ROAR, BOG_COLOURS)}
    out = {}
    for which, (normal, roar, colours) in villains.items():
        standing = from_ascii(normal, colours)
        out[("normal", which)] = standing
        out[("roar", which)] = from_ascii(roar, colours)
        out[("dead", which)] = standing[::-1]  # upside down, as the 2600 does
    return out


def magpie_frames():
    return {"up": from_ascii(MAGPIE_UP, MAGPIE_COLOURS), "down": from_ascii(MAGPIE_DOWN, MAGPIE_COLOURS)}


def item_frames():
    out = {0x09: from_ascii(SWORD, SWORD_COLOURS), 0x11: from_ascii(MAGNET, MAGNET_COLOURS),
           0x10: from_ascii(BOOK, BOOK_COLOURS)}
    for object_number, colours in KEY_COLOURS.items():
        outline = tuple(int(channel * 0.3) for channel in colours["C"])  # a dark shade of the key's colour
        out[object_number] = from_ascii(KEY, {"K": outline, **colours})
    return out


def cast_sheet(path=None):
    sprites = []
    for view in ("down", "up", "right", "left"):
        sprites += pbj_frames()[view]
    villains = villain_frames()
    for which in ("red", "yellow", "green"):
        sprites += [villains[(pose, which)] for pose in ("normal", "roar", "dead")]
    sprites += list(magpie_frames().values()) + list(item_frames().values())
    sprites += [alice_bridge(56, coat="black"), alice_bridge(56, coat="brown"),
                alice_portrait("black"), alice_portrait("brown")]
    cells = []
    for sprite in sprites:
        h, w = sprite.shape[:2]
        cell = np.zeros((max(h, 60) + 4, w + 4, 3), np.uint8)
        cell[:] = (120, 200, 90)  # on grass
        solid = sprite[..., 3:4] > 0
        cell[2:2 + h, 2:2 + w] = np.where(solid, sprite[..., :3], cell[2:2 + h, 2:2 + w])
        cells.append(cell)
    tallest = max(cell.shape[0] for cell in cells)
    padded = [np.pad(cell, ((0, tallest - cell.shape[0]), (0, 2), (0, 0))) for cell in cells]
    row = np.concatenate(padded, axis=1)
    half = row.shape[1] // 2
    cut = next(x for x in range(half, row.shape[1]) if (row[:, x] == 0).all())
    right = row[:, cut:]
    right = np.pad(right, ((0, 0), (0, max(0, cut - right.shape[1])), (0, 0)))[:, :cut]
    sheet = np.concatenate([row[:, :cut], right], axis=0)
    path = path or os.path.join(paths.SHOTS, "snes", "cast.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(sheet).resize((sheet.shape[1] * 5, sheet.shape[0] * 5), Image.NEAREST).save(path)
    return path


def pictures(coat="black"):
    """picture name -> RGBA, as the pack folder has them (content/cast.py names them). The dead dragons
    aren't drawn: the look turns the normal pose upside down."""
    out = {}
    for view in ("down", "up", "right"):  # left = right mirrored
        for i, frame in enumerate(pbj_frames()[view]):
            out[f"hero_{view}_{i}"] = frame
    for (pose, colour), sprite in villain_frames().items():
        if pose != "dead":
            out[f"dragon_{pose}_{colour}"] = sprite
    out["bat_up"], out["bat_down"] = magpie_frames()["up"], magpie_frames()["down"]
    names = {object_number: name for name, object_number in ITEMS.items()}
    for object_number, sprite in item_frames().items():
        out[f"item_{names[object_number]}"] = sprite
    # Alice the bridge: head and front legs, her back (stretched), hind legs and tail
    colours = ALICE_COLOURS[coat]
    head_and_legs = [from_ascii(_ALICE_HEAD, colours), from_ascii(_ALICE_FRONT_LEGS, colours)]
    out["bridge_top"] = np.concatenate(head_and_legs)
    out["bridge_middle"] = from_ascii(_ALICE_STRETCH, colours)
    out["bridge_bottom"] = from_ascii(_ALICE_TAIL, colours)
    out["messenger"] = alice_portrait(coat)
    return out


if __name__ == "__main__":
    save_folder(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cast"), pictures())
    print(cast_sheet())
