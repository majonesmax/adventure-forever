"""Check tools/rebuild_2600.py against the emulator, headless: visit every room (game 1) and run a short real
play (pick up the yellow key, carry it), comparing our re-render with the real frame every frame.
'errors' = pixels the emulator shows that we don't (ignoring the thin-wall columns); 'flicker' = pixels we
draw where the emulator shows floor this frame (objects the 2600 skipped). Saves the worst frames.

Usage: python verify_render.py [outdir]   (default shots/render)
"""

import os
import sys
from typing import Callable, Iterable

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, as a script
from engine import emulator as h
from engine import ram_map as M
from engine.state import Game
from shared.types import Mask, Picture, RamView
from tools import rebuild_2600 as RN

Result = tuple[int, int, str, int, Picture, Picture, Mask]   # error px, flicker px, tag, room, ours,
                                                             # theirs, the error mask



class Render:
    """The running game, our re-render of it, and every frame's comparison so far."""

    def __init__(self) -> None:
        self.core = h.Core()
        self.core.load(os.path.join(h.HERE, "roms", "adventure.a26"))
        memory = self.core.ram
        assert memory is not None   # load() made the live view of the RAM
        self.memory: RamView = memory
        self.game = Game()
        self.rebuild = RN.Rebuild2600(self.game)
        self.results: list[Result] = []
        self.history: list[RamView] = []  # RAM snapshots, newest last

    def run(self, frames: int, keys: Iterable[int] = (), tag: str = "",
            hold: Callable[[], None] | None = None) -> None:
        """Adventure spreads its logic over 3 frames; some runs before the picture is drawn (dragons, bat),
        some after (the hero), and objects are drawn from positions cached a frame earlier ($86-$89). So one
        frame shows a MIX of the last few RAM states. A pixel only counts as wrong if none of the renders of
        the RAM from one frame back, before, and after this retro_run call explains it."""
        self.core.joy = set(keys)
        for _ in range(frames):
            if hold:
                hold()
            before = self.memory.copy()
            self.core.run()
            frame = self.core.frame
            assert frame is not None   # run() has just drawn one
            candidates = [self.history[-1]] if self.history else []
            candidates += [before, self.memory.copy()]
            self.history[:] = [before]
            self.results.append(self.compare(before, candidates, frame, tag))

    def compare(self, before: RamView, candidates: list[RamView], frame: Picture, tag: str) -> Result:
        state = self.game.state(before)
        ours, _ = self.rebuild.draw(state)
        errors, flicker = RN.compare(ours, frame, state.room, self.game.rgb(state.colour(RN.BG_COLOUR)))
        for ram in candidates:
            other = self.game.state(ram)
            if other.room_num != state.room_num:
                continue
            other_render, _ = self.rebuild.draw(other)
            background = self.game.rgb(other.colour(RN.BG_COLOUR))
            other_errors, other_flicker = RN.compare(other_render, frame, other.room, background)
            errors, flicker = errors & other_errors, flicker & other_flicker
        return (int(errors.sum()), int(flicker.sum()), tag, state.room_num, ours, frame.copy(), errors)


def visit_every_room(render: Render) -> None:
    for room in range(1, 0x1F):
        def hold(room: int = room) -> None:
            writes = ((M.ROOM, room), (M.PREV_ROOM, room), (M.HERO_X, 0x50), (M.PREV_X, 0x50),
                      (M.HERO_Y, 0x36), (M.PREV_Y, 0x36))
            for address, value in writes:
                render.memory[address - 0x80] = value
        render.run(8, tag=f"room {room:02X}", hold=hold)


def play_with_the_key(render: Render) -> None:
    """Real play: back to the start, walk to the yellow key, carry it right."""
    render.core.joy = {h.JOY_START}
    for _ in range(10):
        render.core.run()
    render.core.joy = set()
    for _ in range(30):
        render.core.run()
    for _ in range(120):
        x, y = int(render.memory[M.HERO_X - 0x80]), int(render.memory[M.HERO_Y - 0x80])
        keys = ([h.JOY_LEFT] if x > 0x24 else []) + ([h.JOY_UP] if y < 0x3C else [])
        render.run(1, keys, tag="walk to key")
    render.run(40, [h.JOY_RIGHT], tag="carry key")


def steady_frames(results: list[Result]) -> list[Result]:
    """Without the first frames of each segment (a teleport or RESET lands mid-frame), and the boot."""
    seen: dict[str, int] = {}
    steady: list[Result] = []
    for result in results:
        seen[result[2]] = seen.get(result[2], 0) + 1
        if seen[result[2]] > 2 and result[2] != "boot":
            steady.append(result)
    return steady


def report(results: list[Result], out: str) -> None:
    by_tag: dict[str, list[int]] = {}
    for errors, flicker, tag, _room, *_ in results:
        totals = by_tag.setdefault(tag, [0, 0, 0])
        totals[0], totals[1], totals[2] = max(totals[0], errors), max(totals[1], flicker), totals[2] + 1
    for tag, (errors, flicker, frames) in by_tag.items():
        print(f"{tag:12s} frames {frames:3d}  max error px {errors:4d}  max flicker px {flicker:4d}")
    worst = sorted(results, key=lambda result: -result[0])[:4]
    for i, (_errors, _flicker, tag, _room, ours, theirs, error_mask) in enumerate(worst):
        marked = ours.copy()
        marked[error_mask] = (255, 0, 0)
        gap = np.full((228, 4, 3), 255, np.uint8)
        strip = np.concatenate([theirs, gap, ours, gap, marked], axis=1)
        path = os.path.join(out, f"worst_{i}_{tag.replace(' ', '_')}.png")
        Image.fromarray(strip).resize((strip.shape[1] * 2, 228)).save(path)
    total = sum(result[0] for result in results)
    with_errors = sum(1 for result in results if result[0])
    print(f"\n{len(results)} frames; frames with any error: {with_errors}; total error px {total}")


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(h.HERE, "shots", "render")
    os.makedirs(out, exist_ok=True)
    render = Render()
    render.run(60, tag="boot")
    render.run(10, [h.JOY_START], tag="reset")
    render.run(30, tag="start")
    visit_every_room(render)
    play_with_the_key(render)
    report(steady_frames(render.results), out)


if __name__ == "__main__":
    main()
