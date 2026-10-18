"""TEMPLATE PACK - the smallest working pack. The pack is the folder above this one: pack.json and three
pictures (a hero, and one dragon in two poses). This script is how those pictures were made - drawn as text,
one character per pixel, "." = transparent - so they're easy to read and edit:

    python packs/template/source/template_sprites.py   -> packs/template/cast/*.png

You don't need a script: draw the PNGs in any pixel-art editor. To start your own pack, copy the folder:

    cp -r packs/template private/packs/mine        # private/ is git-ignored
    python play.py --pack mine

The full list of pictures a pack can have, and what pack.json can say: content/cast.py and content/world.py.
"""

import os
import sys

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
sys.path.insert(0, REPO_ROOT)
from content.pictures import save_folder
from shared.pixelart import edited, from_ascii

INK, SKIN, SHIRT, GREEN, TOOTH = (24, 24, 40), (232, 184, 136), (64, 120, 216), (72, 168, 72), (248, 248, 240)

HERO = """
...KKKK...
..KSSSSK..
..KSKSKK..
..KSSSSK..
...KSSK...
..KBBBBK..
.KBBBBBBK.
.KSBBBBSK.
..KBBBBK..
..KBKKBK..
..KBK.KBK.
..KK..KK..
.........."""  # the last row stays empty: the feet sit on the row above it

DRAGON = """
....KKKK....
...KGGGGK...
..KGKGGKGK..
..KGGGGGGK..
..KGKKKKGK..
...KGGGGK...
..KGGGGGGK..
.KGGGGGGGGK.
.KGGGGGGGGK.
..KGGGGGGK..
..KGK..KGK..
..KK....KK..
............"""
DRAGON_ROAR = edited(DRAGON, {4: [(3, "KTTTTK")]})  # the same dragon with its teeth showing


def pictures():
    """picture name -> RGBA. Only hero_down_0 is required: with no other hero pictures the look uses it for
    every view (mirrored for walking left). One dragon design (no colour in its name) serves all three; the
    dead pose isn't drawn - the look turns the normal one upside down."""
    return {"hero_down_0": from_ascii(HERO, {"K": INK, "S": SKIN, "B": SHIRT}),
            "dragon_normal": from_ascii(DRAGON, {"K": INK, "G": GREEN}),
            "dragon_roar": from_ascii(DRAGON_ROAR, {"K": INK, "G": GREEN, "T": TOOTH})}


if __name__ == "__main__":
    save_folder(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cast"), pictures())
