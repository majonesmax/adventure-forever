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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, as a script
from app.fonts import mono
from engine import emulator as h
from engine import objects as O
from engine import paths
from engine import rooms as R
from engine.state import Game, GameState, RoomObject
from shared.types import Mask, Picture, Rgb

FRAME_W, FRAME_H = 160, 228
BG_COLOUR = 0x08
HERO_W, HERO_H = 4, 8
SCALE_X, SCALE_Y = 6, 3      # 160x228 -> 960x684 per side (2600 pixels are wide)
JOYSTICK = {pygame.K_UP: h.JOY_UP, pygame.K_DOWN: h.JOY_DOWN, pygame.K_LEFT: h.JOY_LEFT,
            pygame.K_RIGHT: h.JOY_RIGHT, pygame.K_SPACE: h.JOY_B, pygame.K_TAB: h.JOY_SELECT,
            pygame.K_RETURN: h.JOY_START}
Box = tuple[str, tuple[int, int, int, int]]   # (label, (x, y, width, height)) for the overlay


def paint_order(placed: RoomObject) -> tuple[bool, int]:
    """TIA: player 0 is drawn over player 1. The game puts the surround (lit square) and the bridge in
    player 1, and otherwise the lower-numbered object usually lands in player 0 - so paint those two first,
    then the rest from the highest number down (the lowest ends up on top)."""
    return placed[0] not in (0x00, 0x0A), -placed[0]


class Rebuild2600:
    def __init__(self, game: Game):
        self.game = game

    def draw(self, state: GameState) -> tuple[Picture, list[Box]]:
        """-> (160x228x3 uint8 frame, list of (label, box) for the overlay)."""
        img = np.zeros((FRAME_H, FRAME_W, 3), np.uint8)
        top, bottom = R.ROW_LINES[0][0], R.ROW_LINES[-1][1]
        img[top:bottom + 1] = self.game.rgb(state.colour(BG_COLOUR))
        wall = self.game.rgb(state.colour(state.room["colour"]))
        boxes: list[Box] = []
        if state.room["walls_in_front"]:  # TIA priority bit: walls (and the hero, the "ball") over objects
            self.draw_objects(img, state, boxes)
            self.draw_walls(img, state, wall)
            self.draw_hero(img, state, wall, boxes)
        else:
            self.draw_walls(img, state, wall)
            self.draw_hero(img, state, wall, boxes)
            self.draw_objects(img, state, boxes)
        img[:top] = 0
        img[bottom + 1:] = 0
        return img, boxes

    @staticmethod
    def draw_walls(img: Picture, state: GameState, wall: Rgb) -> None:
        top, bottom = R.ROW_LINES[0][0], R.ROW_LINES[-1][1]
        for row, (y0, y1) in enumerate(R.ROW_LINES):
            for col, is_wall in enumerate(state.room["grid"][row]):
                if is_wall:
                    img[y0:y1 + 1, col * 4:col * 4 + 4] = wall
        for flag, (x0, x1) in (("thin_wall_left", R.THIN_WALL_LEFT_X),
                               ("thin_wall_right", R.THIN_WALL_RIGHT_X)):
            if state.room[flag]:
                img[top:bottom + 1, x0:x1 + 1] = wall

    def draw_hero(self, img: Picture, state: GameState, wall: Rgb, boxes: list[Box]) -> None:
        x, y = state.hero
        x0, y0 = x - 2, 224 - 2 * y  # the ball sits one pixel left of where players do
        self._blit_box(img, x0, y0, HERO_W, HERO_H, wall)
        boxes.append(("hero", (x0, y0, HERO_W, HERO_H)))

    def draw_objects(self, img: Picture, state: GameState, boxes: list[Box]) -> None:
        for number, x, y, object_state in sorted(state.objects, key=paint_order):
            obj = self.game.reader.objects[number]
            graphic = O.graphic_for_state(obj, object_state)
            width = obj["width"]
            x0 = x - 1 + (1 if width > 1 else 0)  # TIA: double/quad-size players start one pixel later
            y0 = 224 - 2 * y
            colour = self.game.rgb(state.colour(obj["colour"]))
            for i, byte in enumerate(graphic):
                for bit in range(8):
                    if (byte >> (7 - bit)) & 1:
                        self._blit_box(img, x0 + bit * width, y0 + 2 * i, width, 2, colour)
            if number != 0:
                boxes.append((obj["name"], (x0, y0, 8 * width, 2 * len(graphic))))

    @staticmethod
    def _blit_box(img: Picture, x: int, y: int, w: int, hgt: int, colour: Rgb) -> None:
        x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, FRAME_W), min(y + hgt, FRAME_H)
        if x0 < x1 and y0 < y1:
            img[y0:y1, x0:x1] = colour


def compare(ours: Picture, theirs: Picture, room: dict[str, Any], floor_rgb: Rgb) -> tuple[Mask, Mask]:
    """Pixels the emulator shows that we don't match (= real errors), ignoring the thin-wall columns (their
    2600 colour is borrowed from objects). Pixels we draw that the emulator left as floor are mostly flicker
    (an object the 2600 skipped this frame), so they're counted separately."""
    our_pixels, their_pixels = ours.astype(int), theirs.astype(int)
    differ = np.abs(our_pixels - their_pixels).max(axis=2) > 6
    # the game sets VDELP1: whichever object is in the "player 1" slot this frame appears one line lower,
    # and the slot assignment rotates - so accept a 1-line vertical shift
    for dy in (-1, 1):
        differ &= np.abs(np.roll(our_pixels, dy, axis=0) - their_pixels).max(axis=2) > 6
    for flag, (x0, x1) in (("thin_wall_left", R.THIN_WALL_LEFT_X), ("thin_wall_right", R.THIN_WALL_RIGHT_X)):
        if room[flag]:
            differ[:, x0:x1 + 1] = False
    differ[206:] = False  # the 2600 bleeds the last wall row one line further at the far left - ignore
    floor = np.abs(their_pixels - np.array(floor_rgb)).max(axis=2) <= 6
    return differ & ~floor, differ & floor


class Controls:
    """What the keys have switched: the labels, the diff view, pause - and whether to quit."""

    def __init__(self) -> None:
        self.labels, self.diff_view, self.paused, self.quit = True, False, False, False

    def handle(self, core: h.Core) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                self.quit = True
                return
            if event.type not in (pygame.KEYDOWN, pygame.KEYUP):
                continue
            down = event.type == pygame.KEYDOWN
            if event.key in JOYSTICK:
                (core.joy.add if down else core.joy.discard)(JOYSTICK[event.key])
            elif down and event.key == pygame.K_l:
                self.labels = not self.labels
            elif down and event.key == pygame.K_d:
                self.diff_view = not self.diff_view
            elif down and event.key == pygame.K_p:
                self.paused = not self.paused


def draw_labels(screen: pygame.Surface, font: pygame.font.Font, boxes: list[Box]) -> None:
    """The overlay on the rebuild's side: a box and a name for everything drawn."""
    right_side = FRAME_W * SCALE_X + 16
    for name, (x, y, width, height) in boxes:
        rect = pygame.Rect(right_side + x * SCALE_X, y * SCALE_Y, width * SCALE_X, height * SCALE_Y)
        pygame.draw.rect(screen, (255, 255, 255), rect, 1)
        screen.blit(font.render(name, True, (255, 255, 255), (0, 0, 0)), (rect.x, rect.y - 16))


def info_line(state: GameState, errors_now: int, errors_recent: int) -> str:
    carried = O.NAMES.get(state.carried) if state.carried != 0x12 else "-"
    hero_x, hero_y = state.hero
    return (f"room ${state.room_num:02X} {state.room['name']}   hero {hero_x:02X},{hero_y:02X}   "
            f"carrying {carried}   objects here {len(state.objects)}   "
            f"mismatched px {errors_now} (max/60f {errors_recent})   [L]abels [D]iff [P]ause")


def show(screen: pygame.Surface, frames: tuple[Picture, Picture]) -> None:
    """The emulator's frame on the left, the rebuild on the right, scaled up."""
    screen.fill((16, 16, 24))
    for side, picture in enumerate(frames):
        surf = pygame.surfarray.make_surface(picture.transpose(1, 0, 2))
        scaled = pygame.transform.scale(surf, (FRAME_W * SCALE_X, FRAME_H * SCALE_Y))
        screen.blit(scaled, (side * (FRAME_W * SCALE_X + 16), 0))


def main() -> None:
    core = h.Core()
    core.load(paths.ROM)
    ram = core.ram
    assert ram is not None   # load() made the live view of the RAM
    av_info = core.av_info()
    fps, rate = av_info.timing.fps, int(av_info.timing.sample_rate) or 31440
    game = Game()
    rebuild = Rebuild2600(game)
    pygame.display.init()  # not pygame.init(): that also opens pygame's own audio mixer, a 2nd stream
    pygame.font.init()
    audio = h.AudioOut(rate)
    screen = pygame.display.set_mode((FRAME_W * SCALE_X * 2 + 16, FRAME_H * SCALE_Y + 40))
    pygame.display.set_caption("Adventure - emulator (left) vs our re-render (right)")
    font = mono(14)
    controls = Controls()
    clock = pygame.time.Clock()
    error_history: list[int] = []
    while True:
        controls.handle(core)
        if controls.quit:
            return
        if not controls.paused:
            core.run()
            audio.push(core.take_audio())
        if core.frame is None:
            continue
        state = game.state(ram)
        ours, boxes = rebuild.draw(state)
        errors, flicker = compare(ours, core.frame, state.room, game.rgb(state.colour(BG_COLOUR)))
        error_history = (error_history + [int(errors.sum())])[-60:]
        right = ours.copy()
        if controls.diff_view:
            right[errors] = (255, 0, 0)
            right[flicker] = (255, 160, 0)
        show(screen, (core.frame, right))
        if controls.labels:
            draw_labels(screen, font, boxes)
        info = info_line(state, error_history[-1], max(error_history))
        screen.blit(font.render(info, True, (200, 200, 220)), (8, FRAME_H * SCALE_Y + 12))
        pygame.display.flip()
        clock.tick(fps)


if __name__ == "__main__":
    main()
