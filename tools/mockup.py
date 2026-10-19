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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, when run as a script
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


def to_layout(fx: float, line: float, col_w: int) -> tuple[float, float]:
    """2600 frame coordinates (160 px wide, scan lines 13-205) -> room-space pixels of a layout."""
    return fx * col_w / 4, (line - 13) * ROOM_H / 193


def scene_image(st: GameState, layout: str, reader: O.Reader, hero_spr: Picture,
                font: ImageFont.ImageFont | ImageFont.FreeTypeFont) -> tuple[Picture, Picture, int]:
    L = LAYOUTS[layout]
    col_w = L["col"]
    world = content.load("classic").world
    assert world is not None   # the classic pack has a world
    place = area(st.room["room"])
    room_img = paint_tiles(st.room, world.tile(place, "wall"), world.tile(place, "floor"), (0, 0, 0), 0.6,
                           col_w=col_w)
    # objects (except the lit square), then the hero, in room space
    hx, hy = to_layout(st.hero[0] - 2 + 2, 224 - 2 * st.hero[1] + 4, col_w)  # hero hit-box centre
    for n, x, y, s in sorted(st.objects, key=lambda o: -o[0]):
        if n == 0:
            continue
        obj = reader.objects[n]
        spr = object_sprite(obj, s, col_w)
        ox, oy = to_layout(x - 1 + (1 if obj["width"] > 1 else 0), 224 - 2 * y, col_w)
        blit(room_img, spr, ox - 1, oy - 1)
    blit(room_img, hero_spr, hx - 8, hy - 8)
    if st.room["colour"] == 0x08:  # dark room: torch light around the hero
        yy, xx = np.mgrid[0:room_img.shape[0], 0:room_img.shape[1]]
        d = np.hypot(xx - hx, (yy - hy) * 0.9)
        light = np.clip(1.35 - d / 34.0, 0, 1)
        light = np.round(light * 3) / 3  # NES-style banded falloff
        room_img = (room_img * light[..., None]).astype(np.uint8)
    # place on the 256x240 screen
    screen = np.zeros((SCREEN[1], SCREEN[0], 3), np.uint8)
    cam = 0
    if L["scroll"]:
        cam = int(np.clip(hx - SCREEN[0] / 2, 0, L["room_w"] - SCREEN[0]))
    view = room_img[:, cam:cam + SCREEN[0] - L["room_x"] * 2]
    screen[HUD_H:HUD_H + ROOM_H, L["room_x"]:L["room_x"] + view.shape[1]] = view
    # status bar
    im = Image.fromarray(screen)
    d = ImageDraw.Draw(im)
    d.rectangle([8, 10, 40, 38], outline=NES[0x30])
    d.text((48, 12), "GAME 1", fill=NES[0x30], font=font)
    d.text((48, 26), st.room["name"].upper()[:24], fill=NES[0x10], font=font)
    carried = st.carried if st.carried != 0x12 else None
    if carried is not None:
        spr = object_sprite(reader.objects[carried], 0, 6)
        blit(screen := np.array(im), spr, 24 - spr.shape[1] / 2, 24 - spr.shape[0] / 2)
        im = Image.fromarray(screen)
    return np.array(im), room_img, cam


def capture_states() -> tuple[dict[int, GameState], Game]:
    """Real game-1 states, one per scene room, with the hero in a sensible open spot."""
    c = h.Core()
    c.load(os.path.join(h.HERE, "roms", "adventure.a26"))
    ram = c.ram
    assert ram is not None   # load() made the live view of the RAM
    c.joy = set()
    for _ in range(60):
        c.run()
    c.joy = {h.JOY_START}
    for _ in range(10):
        c.run()
    c.joy = set()
    for _ in range(30):
        c.run()
    ren = Game()
    wanted = {0x11: (0x30, 0x30), 0x04: (0x50, 0x52), 0x0E: (0x60, 0x30), 0x09: (0x2A, 0x28)}
    states: dict[int, GameState] = {}
    for room, _ in SCENES:
        x, y = open_spot(ren.rooms[room], *wanted[room])
        for _ in range(4):
            for a, v in ((M.ROOM, room), (M.PREV_ROOM, room), (M.HERO_X, x), (M.PREV_X, x), (M.HERO_Y, y), (M.PREV_Y, y)):
                ram[a - 0x80] = v
            if room == 0x11:  # carry the yellow key here, so the status bar has something to show
                ram[M.CARRIED - 0x80], ram[M.CARRY_DX - 0x80], ram[M.CARRY_DY - 0x80] = 0x0B * 9, 8, 0
            c.run()
        states[room] = ren.state(ram.copy())
        ram[M.CARRIED - 0x80] = M.NOTHING_CARRIED
    return states, ren


def open_spot(room: dict[str, Any], x: int, y: int) -> Point:
    """Nearest hero position to (x, y) whose 4x8 hit-box (plus a margin) is on floor, not wall."""
    def free(hx: int, hy: int) -> bool:
        x0, line0 = hx - 2, 224 - 2 * hy
        for line in range(line0 - 2, line0 + 10):
            r = next((i for i, (a, b) in enumerate(R.ROW_LINES) if a <= line <= b), None)
            if r is None:
                return False
            for px in range(x0 - 2, x0 + 6):
                if not 0 <= px < 160 or room["grid"][r][px // 4]:
                    return False
        return True
    best = min(((hx, hy) for hx in range(4, 156) for hy in range(0x10, 0x68) if free(hx, hy)),
               key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2)
    return best


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    states, ren = capture_states()
    reader = ren.reader
    cast = content.load("classic").cast
    assert cast is not None   # the classic pack has a cast
    hero = cast.hero()["right"][0]
    font = ImageFont.load_default()
    for layout, L in LAYOUTS.items():
        tiles = []
        for room, _ in SCENES:
            scr, room_img, cam = scene_image(states[room], layout, reader, hero, font)
            Image.fromarray(scr).save(os.path.join(OUT, f"layout_{layout}_room_{room:02X}.png"))
            tiles.append(scr)
            if layout == "B" and room == 0x11:
                # the whole 320 px room with the camera window marked
                full = Image.fromarray(room_img)
                d = ImageDraw.Draw(full)
                d.rectangle([cam, 0, cam + 255, ROOM_H - 1], outline=(255, 255, 255), width=2)
                full.resize((full.width * 3, full.height * 3), Image.Resampling.NEAREST).save(
                    os.path.join(OUT, "layout_B_camera_window.png"))
        # 2x2 sheet at 3x scale with a title
        sheet = Image.new("RGB", (2 * 256 * 3 + 30, 2 * 240 * 3 + 80), (30, 30, 40))
        d = ImageDraw.Draw(sheet)
        d.text((10, 12), L["title"], fill=(240, 240, 240), font=ImageFont.load_default(size=28))
        for i, t in enumerate(tiles):
            im = Image.fromarray(t).resize((256 * 3, 240 * 3), Image.Resampling.NEAREST)
            sheet.paste(im, (10 + (i % 2) * (256 * 3 + 10), 60 + (i // 2) * (240 * 3 + 10)))
        sheet.save(os.path.join(OUT, f"layout_{layout}.png"))
        print(os.path.join(OUT, f"layout_{layout}.png"))


if __name__ == "__main__":
    main()
