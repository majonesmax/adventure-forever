"""An animated GIF of the four-way grid (NES, SNES, the 2600 original, the live RAM) from a recorded take -
for the README and for posts.

The remasters are drawn again from the take's RAM (ram.bin), so the GIF shows the looks, casts and worlds as
they are now (each look's own, unless --cast / --world), with room scrolls where the take had them. The 2600
picture is the take's own recording of it; the RAM panel is rebuilt from ram.bin as it was drawn live.

Usage: python tools/make_gif.py recordings/<take> --start 1300 --end 2140 [-o docs/media/grid.gif]
       [--fps 15] [--width 768] [--cast pbj] [--world pbj]
       -o grid.mp4 makes a video instead (60 fps, H.264), for sites that don't play GIFs (Reddit)
  start / end: the take's video frames (log.jsonl "f"; 60 a second). Needs ffmpeg.
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Iterator

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
from looks.base import RoomLook  # noqa: E402
from shared.types import Picture  # noqa: E402

WARM_UP = 900  # frames of the take the RAM panel sees before the GIF starts, so its event log has history


def ffmpeg() -> str:
    found = find_ffmpeg()
    if found is None:
        raise SystemExit("this needs ffmpeg: https://ffmpeg.org/download.html")
    return found


def frames_2600(take: str, start: int, end: int) -> Iterator[Picture]:
    """The take's 2600 pictures for frames [start, end), as RGB arrays."""
    w, h = json.load(open(os.path.join(take, "meta.json")))["streams"]["a2600"]
    proc = subprocess.Popen([ffmpeg(), "-loglevel", "error", "-i", os.path.join(take, "a2600.mp4"),
                             "-vf", f"select=between(n\\,{start}\\,{end - 1})", "-vsync", "0",
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    size = w * h * 3
    assert proc.stdout is not None   # opened as a pipe
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    proc.wait()


def options() -> argparse.Namespace:
    first_sentence = " ".join((__doc__ or "").split("\n")[:2])
    parser = argparse.ArgumentParser(description=first_sentence)
    parser.add_argument("take")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("-o", "--out", default=os.path.join("docs", "media", "grid.gif"))
    parser.add_argument("--fps", type=int, help="frames a second (default: 15 for a GIF, 60 for a video)")
    parser.add_argument("--width", type=int, default=768, help="the GIF's width (the grid is 1024x960)")
    parser.add_argument("--cast")
    parser.add_argument("--world")
    args = parser.parse_args()
    args.fps = args.fps or (60 if args.out.endswith(".mp4") else 15)
    return args


class Grid:
    """The four-way grid, drawn again frame by frame from a take: both looks from its RAM (with the room
    scrolls the take had), its own 2600 picture, and the RAM panel."""

    def __init__(self, args: argparse.Namespace):
        self.take = args.take
        self.ram = np.fromfile(os.path.join(self.take, "ram.bin"), np.uint8).reshape(-1, 128)
        with open(os.path.join(self.take, "log.jsonl")) as f:
            self.log = [json.loads(line) for line in f]
        self.game = Game()
        self.nes = looks.make("nes", args.cast, args.world, self.game.reader)
        self.snes = looks.make("snes", args.cast, args.world, self.game.reader)
        self.panel, self.tag_font = DP.DebugPanel(QUAD), mono(12, bold=True)
        self.screen = pygame.Surface((2 * QUAD[0], 2 * QUAD[1]))
        self.last_g: int | None = None
        self.scrolls: dict[RoomLook, TR.Scroll] = {}
        self.prev = None

    def warm_up(self, start: int) -> None:
        """The panel's history, and the looks' walk cycle, from the frames before `start`."""
        for i in range(max(0, start - WARM_UP), start):
            self.follow_panel(i)
        self.prev = self.game.state(self.ram[start - 1]) if start else None

    def follow_panel(self, i: int) -> None:
        if self.log[i]["g"] != self.last_g:
            self.panel.update(None, self.ram[i], self.log[i]["g"])
            self.last_g = self.log[i]["g"]

    def pictures(self, i: int) -> dict[RoomLook, Picture]:
        """Both looks' pictures for take frame i: a room scroll's next frame while one slides, as it did
        live, else the room drawn again (and a scroll starting, if the hero just changed rooms)."""
        state = self.game.state(self.ram[i])
        if self.scrolls and self.log[i]["scroll"]:  # sliding into the next room: the game waits
            return {look: scroll.frame() for look, scroll in self.scrolls.items()}
        self.scrolls = {}
        drawn = {look: look.draw(state, i) for look in (self.nes, self.snes)}
        if self.prev is not None and TR.scroll_direction(self.prev, state):
            made = {look: TR.Scroll.between(look, self.prev, state, i) for look in (self.nes, self.snes)}
            self.scrolls = {look: scroll for look, scroll in made.items() if scroll is not None}
            drawn = {look: scroll.frame() for look, scroll in self.scrolls.items()}
        self.prev = state
        return drawn

    def frame(self, picture_2600: Picture, drawn: dict[RoomLook, Picture], i: int) -> bytes:
        """The grid for take frame i, as raw RGB."""
        state = self.game.state(self.ram[i])
        self.screen.fill((16, 16, 24))
        draw_grid(self.screen, picture_2600, (drawn[self.nes], self.nes.name),
                  (drawn[self.snes], self.snes.name), self.panel, state, self.tag_font)
        return pygame.surfarray.array3d(self.screen).transpose(1, 0, 2).tobytes()


def store_frames(grid: Grid, args: argparse.Namespace, raw: str) -> int:
    """Every kept frame of the grid, raw, into the file `raw`; how many were kept."""
    every = 60 // args.fps
    kept = 0
    frames = zip(range(args.start, args.end), frames_2600(grid.take, args.start, args.end))
    with open(raw, "wb") as store:
        for number, (i, picture_2600) in enumerate(frames):
            grid.follow_panel(i)
            drawn = grid.pictures(i)
            if number % every:
                continue
            store.write(grid.frame(picture_2600, drawn, i))
            kept += 1
    return kept


def encode(args: argparse.Namespace, raw: str, encoder: list[str], height: int, palette: str) -> None:
    """The raw frames as the video (whole-pixel scaling, yuv420p so every player takes it) or the GIF (its
    own palette, made from the frames first)."""
    if args.out.endswith(".mp4"):
        with open(raw, "rb") as f:
            subprocess.run(encoder + ["-vf", f"scale={args.width}:{height}:flags=neighbor", "-c:v", "libx264",
                                      "-crf", "14", "-preset", "slow", "-pix_fmt", "yuv420p",
                                      "-movflags", "+faststart", args.out], stdin=f, check=True)
        return
    scale = f"scale={args.width}:{height}:flags=lanczos"
    with open(raw, "rb") as f:
        subprocess.run(encoder + ["-vf", f"{scale},palettegen=stats_mode=diff", palette], stdin=f, check=True)
    use_palette = f"{scale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle"
    with open(raw, "rb") as f:
        subprocess.run(encoder + ["-i", palette, "-lavfi", use_palette, "-loop", "0", args.out],
                       stdin=f, check=True)
    os.remove(palette)


def main() -> None:
    args = options()
    pygame.display.init()
    pygame.font.init()
    grid = Grid(args)
    grid.warm_up(args.start)
    screen = grid.screen
    height = round(args.width * screen.get_height() / screen.get_width() / 2) * 2
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    encoder = [ffmpeg(), "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{screen.get_width()}x{screen.get_height()}", "-r", str(args.fps), "-i", "-"]
    raw = os.path.join(out_dir, ".grid.rgb")
    kept = store_frames(grid, args, raw)
    encode(args, raw, encoder, height, os.path.join(out_dir, ".palette.png"))
    os.remove(raw)
    print(f"{args.out}: {kept} frames, {kept / args.fps:.1f} s, {args.width}x{height}, "
          f"{os.path.getsize(args.out) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
