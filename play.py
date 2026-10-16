"""Adventure Forever: Atari 2600 Adventure, running unmodified in an emulator and redrawn live as an NES game
or a Super NES one, with the 2600 original alongside.

Usage: .venv/bin/python play.py [--look nes|snes|template] [--cast <pack>] [--world <pack>] [--pack <pack>]
                                [--grid] [--public] [--record]
       .venv/bin/python play.py --list          the looks and packs there are

A look is the console (how the game is drawn). A cast is who's in it, a world is where; both come in packs.
Any look shows any cast in any world.

Keys:  arrows + space   joystick + fire (drop an item)      Tab / Enter   GAME SELECT / GAME RESET
       L   next look (NES -> SNES)     C   next cast     W   next world   (classic -> pbj -> your packs)
           (each brings up a moment's overlay naming the look, cast and world; I shows it without a change)
       V   view: side by side -> look only -> 2600 only -> grid
       T   room scrolls on/off      P   pause                M   music on/off      - / =   music volume
       N   next music source        S   screenshot           R   record on/off     D   debug line      Esc   quit

The window itself is app/window.py; looks are in looks/ (looks/base.py), casts and worlds in packs/
(content/cast.py, content/world.py).
"""

import argparse
import os
import signal
import sys

import content
import looks
from app.rom import find_rom
from app.window import GameWindow


def options():
    ap = argparse.ArgumentParser(description="Atari 2600 Adventure, remastered live.")
    ap.add_argument("--look", default=os.environ.get("ADVENTURE_LOOK"),
                    help="start in this look: nes, snes or template (--list shows them)")
    ap.add_argument("--cast", help="start with this pack's cast, on every look (default: each look's own)")
    ap.add_argument("--world", help="start in this pack's world, on every look (default: each look's own)")
    ap.add_argument("--pack", default=os.environ.get("ADVENTURE_PACK"),
                    help="both: this pack's cast in its world (--list shows the packs)")
    ap.add_argument("--list", action="store_true", help="list the looks and packs, then quit")
    ap.add_argument("--grid", action="store_true", help="start in the four-way grid view")
    ap.add_argument("--public", action="store_true",
                    help="exactly what the public release has: no private packs, the built-in music")
    ap.add_argument("--record", action="store_true", help="record from the first frame (needs ffmpeg)")
    args = ap.parse_args()
    if args.list:
        print(looks.listing(args.public))
        sys.exit(0)
    if args.look and looks.look_class(args.look) is None:
        ap.error(f"no look called {args.look!r} - try --list")
    pack = content.load(args.pack) if args.pack and args.pack in content.packs() else None
    args.cast = args.cast or (args.pack if pack is None or pack.cast else None)
    args.world = args.world or (args.pack if pack is None or pack.world else None)
    for part, key in (("cast", args.cast), ("world", args.world)):
        if key:
            try:
                if getattr(content.load(key), part) is None:
                    ap.error(f"pack {key!r} has no {part}")
            except ValueError as err:
                ap.error(str(err))
    return args


def main():
    args = options()
    rom = find_rom()
    if rom is None:
        return
    window = GameWindow(rom, look_key=args.look, cast_key=args.cast, world_key=args.world, grid=args.grid,
                        public=args.public, record=args.record)
    try:
        window.run()
    finally:  # a recording only plays once ffmpeg has been told the stream ended - however the game stops
        window.stop_recording()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # a polite quit still finishes a recording
    main()
