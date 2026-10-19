"""The NES look: Adventure redrawn as an 8-bit NES game - one 256x240 screen, NES colours only.

A RoomLook (looks/base.py): the shared machinery shows the world's rooms and places the cast; this module is
the NES platform:
  rules     every picture - the cast's sprites, the world's rooms and gates - is snapped to the NES palette
  screens   the status bar, the title screen (the gold castle in miniature), the win banner and a
            full-screen CONGRATULATIONS with the hero holding the chalice
Its own pack is "classic" (packs/classic): the knight, the dragons and the bat, in brick castles.
"""

import numpy as np

from engine import rooms as R
from engine.state import GameState
from looks.base import RoomLook
from content.pictures import FLASH
from shared import hud as HUD
from shared import layout as L
from shared.palettes import NES, flash_colour
from shared.pixelart import blit
from shared.types import Picture, Rgb

SCREEN_W, SCREEN_H, HUD_H = L.SCREEN_W, L.SCREEN_H, L.HUD_H
PALETTE = np.array(NES, int)


def nes_colours(picture: Picture, keep: Rgb | None = None) -> Picture:
    """Every pixel (every solid one, for RGBA) -> the nearest NES colour; pixels of colour `keep` are left."""
    out = picture.copy()
    solid = np.ones(out.shape[:2], bool) if out.shape[2] == 3 else out[..., 3] > 0
    if keep is not None:
        solid &= ~np.all(out[..., :3] == keep, axis=2)
    colours, where = np.unique(out[solid][:, :3].astype(int), axis=0, return_inverse=True)
    nearest = PALETTE[((colours[:, None] - PALETTE[None]) ** 2).sum(axis=2).argmin(axis=1)]
    out[solid, :3] = nearest[where.ravel()]
    return out


class NesLook(RoomLook):
    platform = "nes"
    platform_name = "NES REMASTER"
    own_pack = "classic"

    # ---- the platform (the RoomLook methods) ----

    def adapt(self, sprite: Picture) -> Picture:
        """NES colours only (the flashing marker is left for the flash to fill)."""
        return nes_colours(sprite, keep=FLASH)

    def adapt_scenery(self, picture: Picture) -> Picture:
        """NES colours only, for rooms and gates too."""
        return nes_colours(picture)

    def win_splash(self, state: GameState, frame_no: int) -> Picture | None:
        """Full-screen victory (classic 8-bit ending style): the knight holding the chalice up, sparkles,
        flashing CONGRATULATIONS."""
        screen = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
        gold = NES[flash_colour(frame_no, every=4)]
        title = "CONGRATULATIONS"  # 15 letters x 16 px = 240: fits with an 8 px margin (the "!" didn't)
        HUD.draw_text(screen, title, (SCREEN_W - HUD.text_width(title, 2)) // 2, 20, gold, scale=2,
                      shadow=NES[0x07])
        hero, chalice = self.hero["down"][0], self.held_icon(0x10, frame_no)
        k = max(1, 64 // hero.shape[0])  # a 16 px knight x4; taller heroes less, so the chalice fits above
        knight = hero.repeat(k, axis=0).repeat(k, axis=1)
        k = max(1, 42 // chalice.shape[0])  # the 14 px chalice x3
        chalice = chalice.repeat(k, axis=0).repeat(k, axis=1)
        centre_x, feet_y = SCREEN_W // 2, 150
        chalice_top = feet_y - knight.shape[0] - chalice.shape[0] + 6  # held up over his head
        blit(screen, chalice, centre_x - chalice.shape[1] / 2, chalice_top)
        blit(screen, knight, centre_x - knight.shape[1] / 2, feet_y - knight.shape[0])
        self.sparkles(screen, frame_no, centre_x, feet_y - knight.shape[0] - 18)
        blink_on = (frame_no // 30) % 2 == 0
        lines = (("THE CHALICE IS HOME", 166, NES[0x30]), (f"GAME {state.game} COMPLETE", 182, NES[0x28]),
                 ("PRESS ENTER TO PLAY AGAIN" if blink_on else "", 212, NES[0x10]))
        for text, y, colour in lines:
            HUD.draw_text(screen, text, (SCREEN_W - HUD.text_width(text)) // 2, y, colour)
        return screen

    @staticmethod
    def sparkles(screen: Picture, frame_no: int, centre_x: float, centre_y: float) -> None:
        """Little crosses scattered round the chalice, re-scattered every 8 frames."""
        rng = np.random.default_rng(frame_no // 8)
        for _ in range(14):
            angle, distance = rng.uniform(0, 2 * np.pi), rng.uniform(26, 58)
            x = int(centre_x + np.cos(angle) * distance)
            y = int(centre_y + np.sin(angle) * distance * 0.8)
            colour = NES[(0x30, 0x38, 0x28)[rng.integers(3)]]
            screen[y, x - 2:x + 3] = colour
            screen[y - 2:y + 3, x] = colour

    def win_banner(self, screen: Picture, state: GameState, frame_no: int) -> None:
        y0, y1 = 96, 144
        screen[y0:y1, 16:240] = 0
        HUD.frame_box(screen, 16, y0, 239, y1 - 1, NES[0x30])
        colour = NES[flash_colour(frame_no, every=4)]
        msg = "THE CHALICE IS HOME!"
        HUD.draw_text(screen, msg, (SCREEN_W - HUD.text_width(msg)) // 2, y0 + 12, colour)
        msg = "PRESS ENTER TO PLAY AGAIN"
        HUD.draw_text(screen, msg, (SCREEN_W - HUD.text_width(msg)) // 2, y0 + 28, NES[0x10])

    def title_screen(self, state: GameState, frame_no: int) -> Picture:
        screen = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
        title = "ADVENTURE"
        HUD.draw_text(screen, title, (SCREEN_W - HUD.text_width(title, 3)) // 2, 20, NES[0x28], scale=3,
                      shadow=NES[0x07])
        # the gold castle, drawn from its real room data with its real wall tile
        castle = R.decode_room(R.load_rom(), 0x11)
        mini = HUD.mini_room(castle, (255, 0, 255), NES[0x0F], cell_w=3, half_row=6)
        mask = np.all(mini == (255, 0, 255), axis=2)
        tex = self.world.wall_tile(0x11)
        if tex is not None:
            tex = self.adapt_scenery(tex)
            yy, xx = np.mgrid[0:mini.shape[0], 0:mini.shape[1]]
            mini[mask] = tex[yy % tex.shape[0], xx % tex.shape[1]][mask]
        else:
            mini[mask] = NES[0x28]
        x0, y0 = (SCREEN_W - mini.shape[1]) // 2, 62
        screen[y0:y0 + mini.shape[0], x0:x0 + mini.shape[1]] = mini
        game = state.game
        line = f"SELECT GAME  < {game} >"
        HUD.draw_text(screen, line, (SCREEN_W - HUD.text_width(line)) // 2, 152, NES[0x30])
        if (frame_no // 30) % 2 == 0:
            line = "PRESS ENTER TO START"
            HUD.draw_text(screen, line, (SCREEN_W - HUD.text_width(line)) // 2, 174, NES[0x28])
        line = "TAB CHANGES THE GAME"
        HUD.draw_text(screen, line, (SCREEN_W - HUD.text_width(line)) // 2, 190, NES[0x00])
        line = "BY WARREN ROBINETT 1980"
        HUD.draw_text(screen, line, (SCREEN_W - HUD.text_width(line)) // 2, 220, NES[0x00])
        return screen

    def draw_hud(self, screen: Picture, state: GameState, frame_no: int) -> None:
        """Status bar: the carried item in a box (left), the title and game number (centre)."""
        screen[:HUD_H] = 0
        HUD.draw_text(screen, "ITEM", 12, 5, NES[0x10])
        HUD.frame_box(screen, 8, 15, 43, 43, NES[0x30])
        title = "ADVENTURE"
        HUD.draw_text(screen, title, (SCREEN_W - HUD.text_width(title)) // 2, 12, NES[0x28])
        game = f"GAME {state.game}"
        HUD.draw_text(screen, game, (SCREEN_W - HUD.text_width(game)) // 2, 28, NES[0x30])
        if state.carried != 0x12:
            spr = self.held_icon(state.carried, frame_no)
            blit(screen, spr, 26 - spr.shape[1] / 2, 29 - spr.shape[0] / 2)
