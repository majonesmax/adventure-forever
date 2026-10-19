"""Layout mockups for the NES look: the same game moments drawn in two candidate screen layouts.

  A "whole room": 1 column = 6 px, 1 half-row (16 scan lines) = 16 px -> 240x192 room, fits the 256x240
    screen with an 8 px border each side and a 48 px status bar. Original proportions, small sprites.
  B "big-sprite scale": 1 column = 8 px, 1 half-row = 16 px -> 320x192 room; the camera pans horizontally
    (screen shows 256 of 320). Sprites at full NES size (16x16 hero fits a 2-column corridor exactly).

Layout A was chosen and lives on in shared/layout.py; this script keeps both for comparison.
Placeholder art only: procedural brick walls in an NES palette, the 2600 object graphics scaled and
outlined, a hand-drawn 16x16 knight. Object positions are real game state (game 1, from the emulator).

Usage: python mockup.py   -> shots/mockups/*.png
"""

import os
import sys
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, as a script
from engine import emulator as h
from engine import objects as O
from engine import ram_map as M
from engine.state import Game, GameState
from engine import rooms as R
from engine import paths
import content
from content.world import area, paint_tiles
from looks.base import original_graphic as object_sprite
from shared.palettes import BLACK, NES
from shared.pixelart import blit
from shared.types import Picture, Point

OUT = os.path.join(paths.SHOTS, "mockups")

LAYOUTS = {
    "A": {"title": "A - whole room (1 col = 6 px)", "col": 6, "room_x": 8, "room_w": 240, "scroll": False},
    "B": {"title": "B - big-sprite scale (1 col = 8 px, camera pans)", "col": 8, "room_x": 0, "room_w": 320,
          "scroll": True},
}
HUD_H, ROOM_H, SCREEN = 48, 192, (256, 240)
SCENES = [(0x11, "gold"), (0x04, "blue"), (0x0E, "red"), (0x09, "dark")]
Font = ImageFont.ImageFont | ImageFont.FreeTypeFont


def to_layout(frame_x: float, line: float, col_w: int) -> tuple[float, float]:
    """2600 frame coordinates (160 px wide, scan lines 13-205) -> room-space pixels of a layout."""
    return frame_x * col_w / 4, (line - 13) * ROOM_H / 193


def draw_room(state: GameState, col_w: int, reader: O.Reader, hero_sprite: Picture) -> tuple[Picture, float]:
    """The room in a layout's scale: tiles, the objects (but the lit square), the hero, the torch light in
    the dark. -> (picture, the hero's x in it)."""
    world = content.load("classic").world
    assert world is not None   # the classic pack has a world
    place = area(state.room["room"])
    room_img = paint_tiles(state.room, world.tile(place, "wall"), world.tile(place, "floor"), (0, 0, 0), 0.6,
                           col_w=col_w)
    hero_x, hero_y = to_layout(state.hero[0] - 2 + 2, 224 - 2 * state.hero[1] + 4, col_w)  # hit-box centre
    for number, x, y, object_state in sorted(state.objects, key=lambda placed: -placed[0]):
        if number == 0:
            continue
        obj = reader.objects[number]
        sprite = object_sprite(obj, object_state, col_w)
        object_x, object_y = to_layout(x - 1 + (1 if obj["width"] > 1 else 0), 224 - 2 * y, col_w)
        blit(room_img, sprite, object_x - 1, object_y - 1)
    blit(room_img, hero_sprite, hero_x - 8, hero_y - 8)
    if state.room["colour"] == 0x08:  # dark room: torch light around the hero
        yy, xx = np.mgrid[0:room_img.shape[0], 0:room_img.shape[1]]
        distance = np.hypot(xx - hero_x, (yy - hero_y) * 0.9)
        light = np.clip(1.35 - distance / 34.0, 0, 1)
        light = np.round(light * 3) / 3  # NES-style banded falloff
        room_img = (room_img * light[..., None]).astype(np.uint8)
    return room_img, hero_x


def status_bar(screen: Picture, state: GameState, reader: O.Reader, font: Font) -> Picture:
    """The status bar drawn over the top of the screen: a box (with what's carried), the game, the room."""
    picture = Image.fromarray(screen)
    pen = ImageDraw.Draw(picture)
    pen.rectangle([8, 10, 40, 38], outline=NES[0x30])
    pen.text((48, 12), "GAME 1", fill=NES[0x30], font=font)
    pen.text((48, 26), state.room["name"].upper()[:24], fill=NES[0x10], font=font)
    carried = state.carried if state.carried != 0x12 else None
    if carried is not None:
        sprite = object_sprite(reader.objects[carried], 0, 6)
        screen = np.array(picture)
        blit(screen, sprite, 24 - sprite.shape[1] / 2, 24 - sprite.shape[0] / 2)
        picture = Image.fromarray(screen)
    return np.array(picture)


def scene_image(state: GameState, layout: str, reader: O.Reader, hero_sprite: Picture,
                font: Font) -> tuple[Picture, Picture, int]:
    settings = LAYOUTS[layout]
    room_img, hero_x = draw_room(state, settings["col"], reader, hero_sprite)
    screen = np.zeros((SCREEN[1], SCREEN[0], 3), np.uint8)   # placed on the 256x240 screen
    camera = 0
    if settings["scroll"]:
        camera = int(np.clip(hero_x - SCREEN[0] / 2, 0, settings["room_w"] - SCREEN[0]))
    view = room_img[:, camera:camera + SCREEN[0] - settings["room_x"] * 2]
    screen[HUD_H:HUD_H + ROOM_H, settings["room_x"]:settings["room_x"] + view.shape[1]] = view
    return status_bar(screen, state, reader, font), room_img, camera


def capture_states() -> tuple[dict[int, GameState], Game]:
    """Real game-1 states, one per scene room, with the hero in a sensible open spot."""
    core = h.Core()
    core.load(os.path.join(h.HERE, "roms", "adventure.a26"))
    ram = core.ram
    assert ram is not None   # load() made the live view of the RAM
    for frames, held in ((60, set()), (10, {h.JOY_START}), (30, set())):
        core.joy = held
        for _ in range(frames):
            core.run()
    game = Game()
    wanted = {0x11: (0x30, 0x30), 0x04: (0x50, 0x52), 0x0E: (0x60, 0x30), 0x09: (0x2A, 0x28)}
    states: dict[int, GameState] = {}
    for room, _ in SCENES:
        x, y = open_spot(game.rooms[room], *wanted[room])
        for _ in range(4):
            pokes = ((M.ROOM, room), (M.PREV_ROOM, room), (M.HERO_X, x), (M.PREV_X, x), (M.HERO_Y, y),
                     (M.PREV_Y, y))
            for address, value in pokes:
                ram[address - 0x80] = value
            if room == 0x11:  # carry the yellow key here, so the status bar has something to show
                ram[M.CARRIED - 0x80], ram[M.CARRY_DX - 0x80], ram[M.CARRY_DY - 0x80] = 0x0B * 9, 8, 0
            core.run()
        states[room] = game.state(ram.copy())
        ram[M.CARRIED - 0x80] = M.NOTHING_CARRIED
    return states, game


def wall_row(line: int) -> int | None:
    """The wall row a scan line is in, or None (above or below the walls)."""
    for row, (first, last) in enumerate(R.ROW_LINES):
        if first <= line <= last:
            return row
    return None


def open_spot(room: dict[str, Any], x: int, y: int) -> Point:
    """Nearest hero position to (x, y) whose 4x8 hit-box (plus a margin) is on floor, not wall."""
    def free(hero_x: int, hero_y: int) -> bool:
        x0, line0 = hero_x - 2, 224 - 2 * hero_y
        for line in range(line0 - 2, line0 + 10):
            row = wall_row(line)
            if row is None:
                return False
            for pixel in range(x0 - 2, x0 + 6):
                if not 0 <= pixel < 160 or room["grid"][row][pixel // 4]:
                    return False
        return True
    everywhere = ((hero_x, hero_y) for hero_x in range(4, 156) for hero_y in range(0x10, 0x68))
    spots = (spot for spot in everywhere if free(*spot))
    return min(spots, key=lambda spot: (spot[0] - x) ** 2 + (spot[1] - y) ** 2)


def save_camera_window(room_img: Picture, camera: int) -> None:
    """Layout B's whole 320 px room, with the camera's window marked."""
    full = Image.fromarray(room_img)
    pen = ImageDraw.Draw(full)
    pen.rectangle([camera, 0, camera + 255, ROOM_H - 1], outline=(255, 255, 255), width=2)
    full.resize((full.width * 3, full.height * 3), Image.Resampling.NEAREST).save(
        os.path.join(OUT, "layout_B_camera_window.png"))


def save_sheet(layout: str, title: str, tiles: list[Picture]) -> None:
    """A layout's four scenes, 2x2 at 3x scale, with a title."""
    sheet = Image.new("RGB", (2 * 256 * 3 + 30, 2 * 240 * 3 + 80), (30, 30, 40))
    pen = ImageDraw.Draw(sheet)
    pen.text((10, 12), title, fill=(240, 240, 240), font=ImageFont.load_default(size=28))
    for index, tile in enumerate(tiles):
        picture = Image.fromarray(tile).resize((256 * 3, 240 * 3), Image.Resampling.NEAREST)
        sheet.paste(picture, (10 + (index % 2) * (256 * 3 + 10), 60 + (index // 2) * (240 * 3 + 10)))
    sheet.save(os.path.join(OUT, f"layout_{layout}.png"))
    print(os.path.join(OUT, f"layout_{layout}.png"))


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    states, game = capture_states()
    cast = content.load("classic").cast
    assert cast is not None   # the classic pack has a cast
    hero = cast.hero()["right"][0]
    font = ImageFont.load_default()
    for layout, settings in LAYOUTS.items():
        tiles = []
        for room, _ in SCENES:
            screen, room_img, camera = scene_image(states[room], layout, game.reader, hero, font)
            Image.fromarray(screen).save(os.path.join(OUT, f"layout_{layout}_room_{room:02X}.png"))
            tiles.append(screen)
            if layout == "B" and room == 0x11:
                save_camera_window(room_img, camera)
        save_sheet(layout, settings["title"], tiles)


if __name__ == "__main__":
    main()
