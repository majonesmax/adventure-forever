"""Check tools/rebuild_2600.py against the emulator, headless: visit every room (game 1) and run a short real play
(pick up the yellow key, carry it), comparing our re-render with the real frame every frame.
'errors' = pixels the emulator shows that we don't (ignoring the thin-wall columns); 'flicker' = pixels we
draw where the emulator shows floor this frame (objects the 2600 skipped). Saves the worst frames.

Usage: python verify_render.py [outdir]   (default shots/render)
"""

import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, when run as a script
from engine import emulator as h
from engine import ram_map as M
from engine.state import Game
from tools import rebuild_2600 as RN

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(h.HERE, "shots", "render")
os.makedirs(out, exist_ok=True)
c = h.Core()
c.load(os.path.join(h.HERE, "roms", "adventure.a26"))
game = Game()
ren = RN.Rebuild2600(game)
results = []


history = []  # RAM snapshots, newest last


def run(n, keys=(), tag="", hold=None):
    """Adventure spreads its logic over 3 frames; some runs before the picture is drawn (dragons, bat), some
    after (the hero), and objects are drawn from positions cached a frame earlier ($86-$89). So one frame
    shows a MIX of the last few RAM states. A pixel only counts as wrong if none of the renders of the RAM
    from one frame back, before, and after this retro_run call explains it."""
    c.joy = set(keys)
    for _ in range(n):
        if hold:
            hold()
        before = c.ram.copy()
        c.run()
        candidates = [history[-1]] if history else []
        candidates += [before, c.ram.copy()]
        history[:] = [before]
        st = game.state(before)
        ours, _ = ren.draw(st)
        err, flick = RN.compare(ours, c.frame, st.room, game.rgb(st.colour(RN.BG_COLOUR)))
        for ram in candidates:
            st2 = game.state(ram)
            if st2.room_num != st.room_num:
                continue
            o2, _ = ren.draw(st2)
            e2, f2 = RN.compare(o2, c.frame, st2.room, game.rgb(st2.colour(RN.BG_COLOUR)))
            err, flick = err & e2, flick & f2
        results.append((int(err.sum()), int(flick.sum()), tag, st.room_num, ours, c.frame.copy(), err))


run(60, tag="boot")
run(10, [h.JOY_START], tag="reset")
run(30, tag="start")

for n in range(1, 0x1F):
    def hold(n=n):
        for a, v in ((M.ROOM, n), (M.PREV_ROOM, n), (M.X, 0x50), (M.PREV_X, 0x50), (M.Y, 0x36), (M.PREV_Y, 0x36)):
            c.ram[a - 0x80] = v
    run(8, tag=f"room {n:02X}", hold=hold)

# real play: back to the start, walk to the yellow key, carry it right
c.joy = {h.JOY_START}
for _ in range(10):
    c.run()
c.joy = set()
for _ in range(30):
    c.run()
for _ in range(120):
    x, y = int(c.ram[M.X - 0x80]), int(c.ram[M.Y - 0x80])
    keys = ([h.JOY_LEFT] if x > 0x24 else []) + ([h.JOY_UP] if y < 0x3C else [])
    run(1, keys, tag="walk to key")
run(40, [h.JOY_RIGHT], tag="carry key")

# skip the first frames of each segment (a teleport or RESET lands mid-frame)
seen, steady = {}, []
for r in results:
    seen[r[2]] = seen.get(r[2], 0) + 1
    if seen[r[2]] > 2 and r[2] != "boot":
        steady.append(r)
results = steady
by_tag = {}
for e, f, tag, room, *_ in results:
    t = by_tag.setdefault(tag, [0, 0, 0])
    t[0], t[1], t[2] = max(t[0], e), max(t[1], f), t[2] + 1
for tag, (e, f, n) in by_tag.items():
    print(f"{tag:12s} frames {n:3d}  max error px {e:4d}  max flicker px {f:4d}")
worst = sorted(results, key=lambda r: -r[0])[:4]
for i, (e, f, tag, room, ours, theirs, err) in enumerate(worst):
    marked = ours.copy()
    marked[err] = (255, 0, 0)
    strip = np.concatenate([theirs, np.full((228, 4, 3), 255, np.uint8), ours,
                            np.full((228, 4, 3), 255, np.uint8), marked], axis=1)
    Image.fromarray(strip).resize((strip.shape[1] * 2, 228)).save(os.path.join(out, f"worst_{i}_{tag.replace(' ', '_')}.png"))
total = sum(r[0] for r in results)
print(f"\n{len(results)} frames; frames with any error: {sum(1 for r in results if r[0])}; total error px {total}")
