"""See a cast and world without playing: the golden test's game moments (the title, dragons, items, the bridge,
a dark maze, the win...) drawn in each look, as one picture - a row per look, a column per moment.

Made for checking a pack while you work on it, and for AI assistants, which can read the picture but can't
play the game. Needs your ROM and the emulator core, like the tests.

Usage: python tools/preview.py --pack mine                  every look, the pack's cast in its own world
       python tools/preview.py --cast pbj --world classic --look snes,paper
       python tools/preview.py --pack mine --moments title,dragons,win --scale 3
       -> shots/preview/<look(s)>+<cast>@<world>.png  (the path is printed)
Moments: title, start_game1, start_game2, dragons, eaten, items_bat_up, bat_down, carry_sword, bridge,
         dark_maze, dot_room, secret_room, black_gate_half, win, walk_right, walk_up
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import looks  # noqa: E402
from engine import paths  # noqa: E402
from engine.state import Game  # noqa: E402
from shared.types import Picture  # noqa: E402
from tests import golden as G  # noqa: E402  (its game moments)

DEFAULT = "title,start_game1,dragons,items_bat_up,carry_sword,bridge,dark_maze,black_gate_half,win"
TITLE_FRAME = 200  # the title screen once its animations have finished


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pack", help="a pack's cast and world")
    ap.add_argument("--cast", help="a pack's cast (default: --pack, else each look's own)")
    ap.add_argument("--world", help="a pack's world (default: --pack, else each look's own)")
    ap.add_argument("--look", default=",".join(looks.LOOKS), help="looks, comma-separated (default: all)")
    ap.add_argument("--moments", default=DEFAULT, help=f"comma-separated (default: {DEFAULT})")
    ap.add_argument("--scale", type=int, default=2, help="pixels per screen pixel (default 2)")
    args = ap.parse_args()
    cast, world = args.cast or args.pack, args.world or args.pack

    _, title, g1 = G.boot(1)
    _, _, g2 = G.boot(2)
    game = Game()
    moments = G.scenarios(g1, g2, title)
    rows: list[Picture] = []
    for look_key in args.look.split(","):
        row: list[Picture] = []
        for name in args.moments.split(","):
            if name not in moments:
                sys.exit(f"no moment called {name!r}: see --help")
            rams, frames, _ = moments[name]
            look = looks.make(look_key, cast, world, game.reader)  # fresh: no state carried over
            for ram, frame in zip(rams, frames):
                img = look.draw(game.state(ram), TITLE_FRAME if name == "title" else frame)
            row += [img, np.full((img.shape[0], 4, 3), 255, np.uint8)]
        rows += [np.concatenate(row[:-1], axis=1), np.full((4, sum(r.shape[1] for r in row[:-1]), 3), 255, np.uint8)]
    sheet = np.concatenate(rows[:-1], axis=0)
    out_dir = os.path.join(paths.SHOTS, "preview")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{args.look.replace(',', '-')}+{cast or 'own'}@{world or 'own'}.png")
    Image.fromarray(sheet).resize((sheet.shape[1] * args.scale, sheet.shape[0] * args.scale), Image.Resampling.NEAREST).save(out)
    print(out)


if __name__ == "__main__":
    main()
