"""Golden-image test: every look, with every cast in every world, must keep drawing exactly the same pixels.

Builds a fixed set of game moments from the real emulator (boot, reset, then objects placed by writing RAM),
renders each in every look with every cast and world (keys like "nes", "snes+classic", "nes@pbj" - see
looks/base.py), and compares a SHA-256 of each screen with tests/golden_hashes.json. Only hashes are
stored: the tests keep no pictures of the game (whose walls and graphics come from the ROM) - the one gameplay
clip in the repository is the README's demo GIF.

Needs roms/adventure.a26 and the Stella core (cores/), so it runs locally, not in CI.
The references were made with the Stella core 8.0_pre b52ccb02e (tools/get_core.py fetches the newest
build, which may draw a pixel differently someday: if only the 2600-derived parts move, that's the core).

Usage: python tests/golden.py            compare; on a mismatch the screen is saved to
                                                   shots/golden_fail/ so you can look at it
       python tests/golden.py --update   accept the current pictures as the new reference
"""

import hashlib
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import content  # noqa: E402
import looks  # noqa: E402
from app import transitions as TR  # noqa: E402
from engine import emulator as h  # noqa: E402
from engine.state import Game  # noqa: E402

HASHES = os.path.join(ROOT, "tests", "golden_hashes.json")              # public casts and worlds only
PRIVATE_HASHES = os.path.join(ROOT, "private", "golden_hashes.json")   # with a private one (never published)
FAIL_DIR = os.path.join(ROOT, "shots", "golden_fail")


# ---- game moments -------------------------------------------------------------------------------------

def boot(game):
    """The emulator after power-on, GAME SELECT to `game`, RESET: (core, ram copy)."""
    core = h.Core()
    core.load(os.path.join(ROOT, "roms", "adventure.a26"))

    def run(n, keys=()):
        core.joy.clear()
        core.joy.update(keys)
        for _ in range(n):
            core.run()
    run(60)
    for _ in range(game - 1):
        run(8, {h.JOY_SELECT})
        run(20)
    title = core.ram.copy()
    run(8, {h.JOY_START})
    run(60)
    return core, title, core.ram.copy()


def poke(ram, values):
    out = ram.copy()
    for addr, v in values.items():
        out[addr - 0x80] = v
    return out


def place(room, hero, objs=(), extra=None):
    """RAM edits: hero in `room` at `hero`, objects (addr, x, y[, state]) in the same room."""
    v = {0x8A: room, 0x8B: hero[0], 0x8C: hero[1]}
    for addr, x, y, *state in objs:
        v.update({addr: room, addr + 1: x, addr + 2: y})
        if state:
            v[addr + 4] = state[0]
    v.update(extra or {})
    return v


def scenarios(g1, g2, title):
    """name -> (list of RAM snapshots drawn in order, frame numbers to draw them at, indices to hash)."""
    s = {}
    s["title"] = ([title, title], [0, 31], [0, 1])
    s["start_game1"] = ([g1], [0], [0])
    s["start_game2"] = ([g2], [0], [0])
    s["dragons"] = ([poke(g1, place(0x0F, (0x50, 0x20), [(0xA4, 0x30, 0x40, 0), (0xA9, 0x60, 0x40, 3),
                                                           (0xAE, 0x90, 0x40, 1)]))], [0], [0])
    s["eaten"] = ([poke(g1, place(0x11, (0x50, 0x20), [(0xA9, 0x50, 0x24, 2)]))], [0], [0])
    items = [(0xB6, 0x30, 0x30), (0xBF, 0x50, 0x50), (0xC2, 0x70, 0x50), (0xC5, 0x90, 0x50), (0xB3, 0x30, 0x55),
             (0xB9, 0x90, 0x30), (0xCB, 0x60, 0x30, 2)]
    s["items_bat_up"] = ([poke(g1, place(0x01, (0x50, 0x20), items))], [0, 7], [0])
    s["bat_down"] = ([poke(g1, place(0x01, (0x50, 0x20), [(0xCB, 0x60, 0x30, 6)]))], [0], [0])
    s["carry_sword"] = ([poke(g1, place(0x01, (0x50, 0x30), [(0xB6, 0x51, 0x30)],
                                        {0x9D: 0x09 * 9, 0x9E: 1, 0x9F: 0}))], [0], [0])
    s["bridge"] = ([poke(g1, place(0x04, (0x80, 0x30), [(0xBC, 0x40, 0x40)]))], [0], [0])
    s["dark_maze"] = ([poke(g1, place(0x13, (0x50, 0x30)))], [0], [0])
    s["dot_room"] = ([poke(g2, place(int(g2[0xA1 - 0x80]), (int(g2[0xA2 - 0x80]) + 10, int(g2[0xA3 - 0x80]) + 4)))],
                     [0], [0])
    s["secret_room"] = ([poke(g2, place(0x1E, (0x30, 0x20), extra={0xE5: 0x40})),
                         poke(g2, place(0x1E, (0x30, 0x20), extra={0xE5: 0x90}))], [0, 1], [0, 1])
    s["black_gate_half"] = ([poke(g1, place(0x10, (0x50, 0x20), extra={0xCA: 0x10}))], [0], [0])
    s["win"] = ([poke(g1, place(0x12, (0x50, 0x20), [(0xB9, 0x52, 0x20)], {0xDE: 0xFF}))] * 2, [0, 120], [0, 1])
    walk = [poke(g1, place(0x01, (0x40 + k, 0x30))) for k in range(14)]  # walking right: side view, stride
    s["walk_right"] = (walk, list(range(14)), [13])
    up = [poke(g1, place(0x01, (0x40, 0x30 + k))) for k in range(14)]   # walking up: back view
    s["walk_up"] = (up, list(range(14)), [13])
    return s


# ---- rendering + hashing ------------------------------------------------------------------------------

def digest(img):
    return hashlib.sha256(np.ascontiguousarray(img, np.uint8).tobytes()).hexdigest()[:16]


def render_all():
    core, title, g1 = boot(1)
    _, _, g2 = boot(2)
    game = Game()
    reader = game.reader
    out, screens, public = {}, {}, set()
    for look_key in {**looks.LOOKS, **looks.TEMPLATE_LOOKS}:
        for cast_key, world_key in [(c, w) for c in content.casts(examples=True) for w in content.worlds(examples=True)]:
            make = lambda reader: looks.make(look_key, cast_key, world_key, reader)  # fresh: no state carried over
            look_name = make(reader).key
            if not (content.is_private(cast_key) or content.is_private(world_key)):
                public.add(look_name)
            for name, (rams, frames, keep) in scenarios(g1, g2, title).items():
                look = make(reader)
                for i, (ram, f) in enumerate(zip(rams, frames)):
                    img = look.draw(game.state(ram), f)
                    if i in keep:
                        key = f"{look_name}/{name}/{i}"
                        out[key], screens[key] = digest(img), img
            # a room scroll, halfway: old room and new room both drawn without actors, the hero carried across
            look = make(reader)
            a = game.state(poke(g1, place(0x11, (0x50, 0x0F))))
            b = game.state(poke(g1, place(0x02, (0x50, 0x69))))
            sc = TR.Scroll.between(look, a, b, 0)
            for k in range(16):
                img = sc.frame()
            key = f"{look_name}/scroll_down/16"
            out[key], screens[key] = digest(img), img
    return out, screens, public


def split(hashes, public):
    """(hashes with public packs, hashes with private packs)."""
    pub = {k: v for k, v in hashes.items() if k.split("/")[0] in public}
    return pub, {k: v for k, v in hashes.items() if k not in pub}


def main():
    hashes, screens, public = render_all()
    pub, priv = split(hashes, public)
    if "--update" in sys.argv:
        with open(HASHES, "w") as f:
            json.dump(pub, f, indent=1, sort_keys=True)
        if priv:
            with open(PRIVATE_HASHES, "w") as f:
                json.dump(priv, f, indent=1, sort_keys=True)
        print(f"golden: {len(pub)} public + {len(priv)} private reference hashes written")
        return 0
    ref = {}
    for path in (HASHES, PRIVATE_HASHES):
        if os.path.exists(path):
            with open(path) as f:
                ref.update(json.load(f))
    ref = {k: v for k, v in ref.items() if k.split("/")[0] in {key.split("/")[0] for key in hashes}}
    bad = [k for k in sorted(ref) if hashes.get(k) != ref[k]]
    missing = [k for k in sorted(hashes) if k not in ref]
    if bad:
        from PIL import Image
        os.makedirs(FAIL_DIR, exist_ok=True)
        for k in bad:
            if k in screens:
                Image.fromarray(screens[k]).save(os.path.join(FAIL_DIR, k.replace("/", "__") + ".png"))
    print(f"golden: {len(ref) - len(bad)}/{len(ref)} match" + (f"; DIFFER: {bad}" if bad else "")
          + (f"; new (not in reference): {missing}" if missing else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
