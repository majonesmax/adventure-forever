"""Every look - the one place that lists them.

A LOOK is the console (NES, SNES, VGA, paper): how the game is drawn. What's drawn - a CAST (who) in a WORLD
(where) - comes from packs, found by content/. Any look shows any cast in any world.

    LOOKS              {key: look class} in the order L cycles them
    TEMPLATE_LOOKS     the template look: reachable with `play.py --look template`, not in the L cycle
    make(look, cast, world, reader)    the look showing that cast in that world (None: the look's own)

To add a look of your own to the L cycle, add it to LOOKS below (looks/template_look.py is the smallest one).
"""

import os

import content
from engine import paths
from looks.nes.look import NesLook
from looks.snes.look import SnesLook
from looks.vga.look import VgaLook
from looks.paper.look import PaperLook
from looks.template_look import TemplateLook

LOOKS = {"nes": NesLook, "snes": SnesLook, "vga": VgaLook, "paper": PaperLook}
TEMPLATE_LOOKS = {"template": TemplateLook}
OLD_NAMES = {"16bit": "snes", "forever": "snes"}  # what the SNES look used to be called


def look_class(key):
    """The look class for a --look name (old names too), or None."""
    key = OLD_NAMES.get(key, key)
    return LOOKS.get(key) or TEMPLATE_LOOKS.get(key)


def make(look_key, cast_key, world_key, reader):
    """The look `look_key` showing `cast_key`'s cast in `world_key`'s world (None: the look's own pack's)."""
    cls = look_class(look_key)
    if cls is None:
        raise ValueError(f"no look called {look_key!r} (play.py --list shows them)")
    cast = content.load(cast_key or cls.own_pack).cast
    world = content.load(world_key or cls.own_pack).world
    if cast is None:
        raise ValueError(f"pack {cast_key!r} has no cast")
    if world is None:
        raise ValueError(f"pack {world_key!r} has no world")
    return cls(reader, cast, world)


def listing(public=False):
    """What --list prints."""
    lines = ["looks (--look, L cycles them):"]
    for key, cls in {**LOOKS, **TEMPLATE_LOOKS}.items():
        extra = "" if key in LOOKS else "   (example; not in the L cycle)"
        lines.append(f"  {key:<16}{cls.platform_name:<20}its own pack: {cls.own_pack}{extra}")
    lines.append("packs (--cast: C cycles their casts; --world: W cycles their worlds):")
    for key, folder in content.packs(public).items():
        try:
            pack = content.load(key)
            parts = []
            if pack.cast:
                parts.append(f"cast {pack.cast.name}")
            if pack.world:
                parts.append(f"world {pack.world.name}")
            what = ", ".join(parts)
        except Exception as err:  # a broken pack is listed, with what's wrong
            what = f"NOT LOADED: {err}"
        where = "" if paths.FROZEN else os.path.relpath(folder, paths.ROOT)
        extra = "   (example; not in the cycles)" if key in content.EXAMPLES else ""
        lines.append(f"  {key:<16}{what:<48}{where}{extra}")
    return "\n".join(lines)
