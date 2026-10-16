"""An animated GIF of the four-way grid (NES, SNES, the 2600 original, the live RAM) from a recorded take - for
the README and for posts.

The remasters are drawn again from the take's RAM (ram.bin), so the GIF shows the looks, casts and worlds as
they are now (each look's own, unless --cast / --world), with room scrolls where the take had them. The 2600
picture is the take's own recording of it; the RAM panel is rebuilt from ram.bin as it was drawn live.

Usage: python tools/make_gif.py recordings/<take> --start 1300 --end 2140 [-o docs/media/grid.gif]
       [--fps 15] [--width 768] [--cast pbj] [--world pbj]
  start / end: the take's video frames (log.jsonl "f"; 60 a second). Needs ffmpeg.
"""

import argparse
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

import looks  # noqa: E402
from app import debug_panel as DP  # noqa: E402
from app import transitions as TR  # noqa: E402
from app.fonts import mono  # noqa: E402
from app.recorder import find_ffmpeg  # noqa: E402
from app.window import QUAD, draw_grid  # noqa: E402
from engine.state import Game  # noqa: E402

WARM_UP = 900  # frames of the take the RAM panel sees before the GIF starts, so its event log has history


def frames_2600(take, start, end):
    """The take's 2600 pictures for frames [start, end), as RGB arrays."""
    w, h = json.load(open(os.path.join(take, "meta.json")))["streams"]["a2600"]
    proc = subprocess.Popen([find_ffmpeg(), "-loglevel", "error", "-i", os.path.join(take, "a2600.mp4"),
                             "-vf", f"select=between(n\\,{start}\\,{end - 1})", "-vsync", "0",
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    size = w * h * 3
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    proc.wait()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("take")
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("-o", "--out", default=os.path.join("docs", "media", "grid.gif"))
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--width", type=int, default=768, help="the GIF's width (the grid is 1024x960)")
    ap.add_argument("--cast")
    ap.add_argument("--world")
    args = ap.parse_args()
    pygame.display.init()
    pygame.font.init()

    take = args.take
    ram = np.fromfile(os.path.join(take, "ram.bin"), np.uint8).reshape(-1, 128)
    with open(os.path.join(take, "log.jsonl")) as f:
        log = [json.loads(line) for line in f]
    game = Game()
    nes = looks.make("nes", args.cast, args.world, game.reader)
    snes = looks.make("snes", args.cast, args.world, game.reader)
    panel, tag_font = DP.DebugPanel(QUAD), mono(12, bold=True)
    screen = pygame.Surface((2 * QUAD[0], 2 * QUAD[1]))

    last_g = None
    for i in range(max(0, args.start - WARM_UP), args.start):  # the panel's history, and the looks' walk cycle
        if log[i]["g"] != last_g:
            panel.update(None, ram[i], log[i]["g"])
            last_g = log[i]["g"]
    prev = game.state(ram[args.start - 1]) if args.start else None

    height = round(args.width * screen.get_height() / screen.get_width() / 2) * 2
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    every = 60 // args.fps
    palette = os.path.join(out_dir, ".palette.png")
    encode = [find_ffmpeg(), "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
              "-s", f"{screen.get_width()}x{screen.get_height()}", "-r", str(args.fps), "-i", "-"]
    raw = os.path.join(out_dir, ".grid.rgb")
    scrolls, kept = {}, 0
    with open(raw, "wb") as store:
        for n, (i, picture_2600) in enumerate(zip(range(args.start, args.end), frames_2600(take, args.start, args.end))):
            r = log[i]
            if r["g"] != last_g:
                panel.update(None, ram[i], r["g"])
                last_g = r["g"]
            st = game.state(ram[i])
            if scrolls and r["scroll"]:  # sliding into the next room: the game waits, as it did live
                pics = {lk: sc.frame() for lk, sc in scrolls.items()}
            else:
                scrolls = {}
                pics = {lk: lk.draw(st, i) for lk in (nes, snes)}
                if prev is not None and TR.scroll_direction(prev, st):
                    scrolls = {lk: TR.Scroll.between(lk, prev, st, i) for lk in (nes, snes)}
                    pics = {lk: sc.frame() for lk, sc in scrolls.items()}
                prev = st
            if n % every:
                continue
            screen.fill((16, 16, 24))
            draw_grid(screen, picture_2600, (pics[nes], nes.name), (pics[snes], snes.name), panel, st, tag_font)
            store.write(pygame.surfarray.array3d(screen).transpose(1, 0, 2).tobytes())
            kept += 1
    scale = f"scale={args.width}:{height}:flags=lanczos"
    with open(raw, "rb") as f:
        subprocess.run(encode + ["-vf", f"{scale},palettegen=stats_mode=diff", palette], stdin=f, check=True)
    with open(raw, "rb") as f:
        subprocess.run(encode + ["-i", palette, "-lavfi", f"{scale}[x];[x][1:v]paletteuse=dither=bayer:"
                                 "bayer_scale=4:diff_mode=rectangle", "-loop", "0", args.out], stdin=f, check=True)
    os.remove(raw)
    os.remove(palette)
    print(f"{args.out}: {kept} frames, {kept / args.fps:.1f} s, {args.width}x{height}, "
          f"{os.path.getsize(args.out) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
