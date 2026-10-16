"""The classic pack's items and bat, drawn by hand in NES colours. K = black outline, other letters per item (COLOURS below).
The chalice's C pixels are FLASH (magenta): the look fills them with the game's flashing colour.

Usage: python packs/classic/source/items.py   -> packs/classic/cast/item_*.png, bat_*.png
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))  # the repo root
from content.pictures import FLASH, save_folder
from shared.palettes import NES
from shared.pixelart import from_ascii

SWORD = """
...........KK...
.KKKKKKKKKKGGK..
KWWWWWWWWWWGGGGK
.KKKKKKKKKKGGK..
...........KK..."""

KEY = """
...........KKKK.
..........KCCCCK
.KKKKKKKKKKCKKCK
KCCCCCCCCCCCKKCK
KCKCKKKKKKKCKKCK
KCKCK.....KCCCCK
KKKKK......KKKK."""

CHALICE = """
..KK........KK..
..KCK......KCK..
..KCCK....KCCK..
..KCWCKKKKCCCK..
...KCWCCCCCCK...
...KCCWCCCCCK...
....KCCCCCCK....
.....KCCCCK.....
......KCCK......
......KCCK......
......KCCK......
.....KCCCCK.....
....KCCCCCCK....
....KKKKKKKK...."""

MAGNET = """
....KKKKKKKK....
...KRRRRRRRRK...
..KRRWRRRRRRRK..
..KRRKKKKKKRRK..
..KRRK....KRRK..
..KRRK....KRRK..
..KRRK....KRRK..
..KRRK....KRRK..
..KRRK....KRRK..
..KSSK....KSSK..
..KSSK....KSSK..
..KKKK....KKKK.."""

BAT_UP = """
K..............K
KK............KK
KPK....KK....KPK
KPPK..KPPK..KPPK
KPPPKKPPPPKKPPPK
.KPPPPPWPPWPPPK.
..KKPPPPPPPPKK..
....KKPKKPKK....
......K..K......"""

BAT_DOWN = """
......KKKK......
.....KPPPPK.....
....KPWPPWPK....
.KKKPPPPPPPPKKK.
KPPPPPPPPPPPPPPK
KPPKKPPPPPPKKPPK
KPK..KPKKPK..KPK
KK....K..K....KK
K..............K"""

K, WHITE, GREY = 0x0F, 0x30, 0x10
ITEMS = {  # picture name -> (art, colours as NES palette indices)
    "item_sword": (SWORD, {"K": K, "W": WHITE, "G": 0x28}),
    "item_key_gold": (KEY, {"K": K, "C": 0x28}),
    "item_key_white": (KEY, {"K": K, "C": WHITE}),
    "item_key_black": (KEY, {"K": K, "C": 0x2D}),
    "item_chalice": (CHALICE, {"K": K, "C": FLASH, "W": WHITE}),
    "item_magnet": (MAGNET, {"K": K, "R": 0x16, "S": GREY, "W": WHITE}),
    "bat_up": (BAT_UP, {"K": K, "P": 0x13, "W": WHITE}),
    "bat_down": (BAT_DOWN, {"K": K, "P": 0x13, "W": WHITE}),
}


def pictures():
    """picture name -> RGBA sprite."""
    return {name: from_ascii(art, {ch: c if isinstance(c, tuple) else NES[c] for ch, c in colours.items()})
            for name, (art, colours) in ITEMS.items()}


if __name__ == "__main__":
    save_folder(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cast"), pictures())
