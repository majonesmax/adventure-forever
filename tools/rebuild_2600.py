"""The 2600 picture, rebuilt from game state alone (RAM + the ROM's tables) - the check that our reading of
the game is complete: tests/verify_render.py compares it pixel for pixel with the emulator's real frame.

Differences from the real thing, on purpose: every object in the room is drawn every frame (the 2600 can only
draw two per frame and takes turns - the flicker), and carried items are drawn at hero + carry offset.

Usage: python tools/rebuild_2600.py      the emulator (left) beside the rebuild (right)
Keys: arrows + space = joystick, Tab = GAME SELECT, Enter = RESET, L = labels/boxes overlay,
      D = diff view (red = pixels where we disagree with the emulator), P = pause, Esc = quit.
"""

import os
import sys
from typing import Any

import numpy as np
import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, when run as a script
from app.fonts import mono
from engine import emulator as h
from engine import objects as O
from engine import paths
from engine import rooms as R
from engine.state import Game, GameState
from shared.types import Mask, Picture, Rgb

FRAME_W, FRAME_H = 160, 228
BG_COLOUR = 0x08
HERO_W, HERO_H = 4, 8
Box = tuple[str, tuple[int, int, int, int]]   # (label, (x, y, width, height)) for the overlay


class Rebuild2600:
    def __init__(self, game: Game):
        self.game = game

    def draw(self, st: GameState) -> tuple[Picture, list[Box]]:
        """-> (160x228x3 uint8 frame, list of (label, box) for the overlay)."""
        img = np.zeros((FRAME_H, FRAME_W, 3), np.uint8)
        top, bottom = R.ROW_LINES[0][0], R.ROW_LINES[-1][1]
        img[top:bottom + 1] = self.game.rgb(st.colour(BG_COLOUR))
        wall = self.game.rgb(st.colour(st.room["colour"]))
        boxes: list[Box] = []

        def draw_walls() -> None:
            for r, (y0, y1) in enumerate(R.ROW_LINES):
                for col, b in enumerate(st.room["grid"][r]):
                    if b:
                        img[y0:y1 + 1, col * 4:col * 4 + 4] = wall
            for flag, (x0, x1) in (("thin_wall_left", R.THIN_WALL_LEFT_X),
                                   ("thin_wall_right", R.THIN_WALL_RIGHT_X)):
                if st.room[flag]:
                    img[top:bottom + 1, x0:x1 + 1] = wall

        def draw_hero() -> None:
            x, y = st.hero
            x0, y0 = x - 2, 224 - 2 * y  # the ball sits one pixel left of where players do
            self._blit_box(img, x0, y0, HERO_W, HERO_H, wall)
            boxes.append(("hero", (x0, y0, HERO_W, HERO_H)))

        def draw_objects() -> None:
            # TIA: player 0 is drawn over player 1. The game puts the surround (lit square) and the bridge in
            # player 1, and otherwise the lower-numbered object usually lands in player 0 - so paint those
            # two first, then the rest from the highest number down (lowest ends up on top)
            for n, x, y, s in sorted(st.objects, key=lambda o: (o[0] not in (0x00, 0x0A), -o[0])):
                obj = self.game.reader.objects[n]
                g = O.graphic_for_state(obj, s)
                w = obj["width"]
                x0 = x - 1 + (1 if w > 1 else 0)  # TIA: double/quad-size players start one pixel later
                y0 = 224 - 2 * y
                colour = self.game.rgb(st.colour(obj["colour"]))
                for i, byte in enumerate(g):
                    for b in range(8):
                        if (byte >> (7 - b)) & 1:
                            self._blit_box(img, x0 + b * w, y0 + 2 * i, w, 2, colour)
                if n != 0:
                    boxes.append((obj["name"], (x0, y0, 8 * w, 2 * len(g))))

        if st.room["walls_in_front"]:  # TIA priority bit: walls (and the hero, the "ball") over objects
            draw_objects()
            draw_walls()
            draw_hero()
        else:
            draw_walls()
            draw_hero()
            draw_objects()
        img[:top] = 0
        img[bottom + 1:] = 0
        return img, boxes

    @staticmethod
    def _blit_box(img: Picture, x: int, y: int, w: int, hgt: int, colour: Rgb) -> None:
        x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, FRAME_W), min(y + hgt, FRAME_H)
        if x0 < x1 and y0 < y1:
            img[y0:y1, x0:x1] = colour


def compare(ours: Picture, theirs: Picture, room: dict[str, Any], floor_rgb: Rgb) -> tuple[Mask, Mask]:
    """Pixels the emulator shows that we don't match (= real errors), ignoring the thin-wall columns (their
    2600 colour is borrowed from objects). Pixels we draw that the emulator left as floor are mostly flicker
    (an object the 2600 skipped this frame), so they're counted separately."""
    a, b = ours.astype(int), theirs.astype(int)
    differ = np.abs(a - b).max(axis=2) > 6
    # the game sets VDELP1: whichever object is in the "player 1" slot this frame appears one line lower,
    # and the slot assignment rotates - so accept a 1-line vertical shift
    for dy in (-1, 1):
        differ &= np.abs(np.roll(a, dy, axis=0) - b).max(axis=2) > 6
    for flag, (x0, x1) in (("thin_wall_left", R.THIN_WALL_LEFT_X), ("thin_wall_right", R.THIN_WALL_RIGHT_X)):
        if room[flag]:
            differ[:, x0:x1 + 1] = False
    differ[206:] = False  # the 2600 bleeds the last wall row one line further at the far left - ignore
    floor = np.abs(b - np.array(floor_rgb)).max(axis=2) <= 6
    return differ & ~floor, differ & floor


def main() -> None:
    core = h.Core()
    core.load(paths.ROM)
    ram = core.ram
    assert ram is not None   # load() made the live view of the RAM
    av = core.av_info()
    fps, rate = av.timing.fps, int(av.timing.sample_rate) or 31440
    game = Game()
    ren = Rebuild2600(game)
    pygame.display.init()  # not pygame.init(): that also opens pygame's own audio mixer, a 2nd stream on the card
    pygame.font.init()
    audio = h.AudioOut(rate)
    sx, sy = 6, 3  # 160x228 -> 960x684 per side (2600 pixels are wide)
    screen = pygame.display.set_mode((FRAME_W * sx * 2 + 16, FRAME_H * sy + 40))
    pygame.display.set_caption("Adventure - emulator (left) vs our re-render (right)")
    font = mono(14)
    joymap = {pygame.K_UP: h.JOY_UP, pygame.K_DOWN: h.JOY_DOWN, pygame.K_LEFT: h.JOY_LEFT,
              pygame.K_RIGHT: h.JOY_RIGHT, pygame.K_SPACE: h.JOY_B, pygame.K_TAB: h.JOY_SELECT,
              pygame.K_RETURN: h.JOY_START}
    labels, diff_view, paused = True, False, False
    clock = pygame.time.Clock()
    err_hist: list[int] = []
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                return
            if e.type in (pygame.KEYDOWN, pygame.KEYUP):
                down = e.type == pygame.KEYDOWN
                if e.key in joymap:
                    (core.joy.add if down else core.joy.discard)(joymap[e.key])
                elif down and e.key == pygame.K_l:
                    labels = not labels
                elif down and e.key == pygame.K_d:
                    diff_view = not diff_view
                elif down and e.key == pygame.K_p:
                    paused = not paused
        if not paused:
            core.run()
            audio.push(core.take_audio())
        if core.frame is None:
            continue
        st = game.state(ram)
        ours, boxes = ren.draw(st)
        errors, flicker = compare(ours, core.frame, st.room, game.rgb(st.colour(BG_COLOUR)))
        err_hist = (err_hist + [int(errors.sum())])[-60:]
        right = ours.copy()
        if diff_view:
            right[errors] = (255, 0, 0)
            right[flicker] = (255, 160, 0)
        screen.fill((16, 16, 24))
        for i, img in enumerate((core.frame, right)):
            surf = pygame.surfarray.make_surface(img.transpose(1, 0, 2))
            screen.blit(pygame.transform.scale(surf, (FRAME_W * sx, FRAME_H * sy)), (i * (FRAME_W * sx + 16), 0))
        if labels:
            ox = FRAME_W * sx + 16
            for name, (x, y, w, hh) in boxes:
                r = pygame.Rect(ox + x * sx, y * sy, w * sx, hh * sy)
                pygame.draw.rect(screen, (255, 255, 255), r, 1)
                screen.blit(font.render(name, True, (255, 255, 255), (0, 0, 0)), (r.x, r.y - 16))
        carried = O.NAMES.get(st.carried) if st.carried != 0x12 else "-"
        info = (f"room ${st.room_num:02X} {st.room['name']}   hero {st.hero[0]:02X},{st.hero[1]:02X}   "
                f"carrying {carried}   objects here {len(st.objects)}   "
                f"mismatched px {err_hist[-1]} (max/60f {max(err_hist)})   [L]abels [D]iff [P]ause")
        screen.blit(font.render(info, True, (200, 200, 220)), (8, FRAME_H * sy + 12))
        pygame.display.flip()
        clock.tick(fps)


if __name__ == "__main__":
    main()
