"""The VGA look: Adventure redrawn as an early-90s PC adventure game (the Sierra / LucasArts era) - 256
colours, dithered light, a grey menu strip, message boxes.

A RoomLook (looks/base.py): the shared machinery shows the world's rooms and places the cast; this module is
the VGA platform:
  rules     one 252-colour palette, a 6 x 7 x 6 colour cube (how many DOS games laid out VGA's 256 colours):
            the world's rooms are reduced to it with ORDERED DITHERING - the cross-hatched gradients of the
            era - while the cast's sprites and the gates snap to its nearest colours, as drawn sprites were
  screens   a status bar with a grey menu strip, the place's name and what you carry; a DOS prompt before the
            title; the win in a message box
Its own pack is "classic"; it was made for moody, liminal worlds.
"""

import numpy as np

from engine import rooms as R
from content.pictures import FLASH
from looks.base import RoomLook
from shared import hud as HUD
from shared import layout as L
from shared.pixelart import blit

LEVELS = (np.linspace(0, 255, 6), np.linspace(0, 255, 7), np.linspace(0, 255, 6))  # R, G, B: 6 x 7 x 6 = 252
BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], float) / 16 - 0.5 + 1 / 32
GREY, LIGHT, DARK, INK, PAPER = (170, 170, 170), (255, 255, 255), (85, 85, 85), (0, 0, 0), (232, 232, 220)
BAR_BG, BLUE = (16, 16, 24), (0, 0, 170)


def to_palette(rgb, dither):
    """RGB (h, w, 3) -> the 6x7x6 cube; with ordered dithering if `dither`."""
    out = np.empty_like(rgb)
    h, w = rgb.shape[:2]
    noise = np.tile(BAYER, (h // 4 + 1, w // 4 + 1))[:h, :w] if dither else 0
    for channel, levels in enumerate(LEVELS):
        step = levels[1] - levels[0]
        value = rgb[..., channel].astype(float) + noise * step
        nearest_level = np.clip(np.round(value / step), 0, len(levels) - 1).astype(int)
        out[..., channel] = levels[nearest_level]
    return out


def bevel(img, x0, y0, x1, y1, raised=True):
    """A Windows-3.1 style bevel: light top-left, dark bottom-right (or the other way round, sunken)."""
    lit, shadowed = (LIGHT, DARK) if raised else (DARK, LIGHT)
    img[y0, x0:x1 + 1] = lit
    img[y0:y1 + 1, x0] = lit
    img[y1, x0:x1 + 1] = shadowed
    img[y0:y1 + 1, x1] = shadowed


class VgaLook(RoomLook):
    platform = "vga"
    platform_name = "VGA REMASTER"
    own_pack = "classic"

    # ---- the platform (the RoomLook methods) ----

    def adapt(self, sprite):
        """Sprites: the nearest palette colours, no dither (the flashing marker is left for the flash)."""
        out = sprite.copy()
        keep = np.all(out[..., :3] == FLASH, axis=2)
        out[..., :3] = to_palette(out[..., :3], dither=False)
        out[keep, :3] = FLASH
        return out

    def adapt_scenery(self, picture):
        """Rooms: the palette, ordered-dithered (smooth light becomes cross-hatching). Gates (RGBA, small and
        hard-edged): the nearest palette colours, like sprites."""
        out = picture.copy()
        out[..., :3] = to_palette(picture[..., :3], dither=picture.shape[2] == 3)
        return out

    def menu_strip(self, screen):
        """The grey strip along the top, with menu words - a PC program's window, not a console's."""
        screen[0:11] = GREY
        screen[11] = DARK
        x = 6
        for word in ("ADVENTURE", "FILE", "GAME", "SOUND"):
            HUD.draw_text(screen, word, x, 2, INK, shadow=None)
            x += HUD.text_width(word) + 14

    def draw_hud(self, screen, state, frame_no):
        screen[:L.HUD_H] = BAR_BG
        self.menu_strip(screen)
        place = self.world.area_name(state.room_num)
        HUD.draw_text(screen, place, 52, 18, PAPER, shadow=None)
        HUD.draw_text(screen, f"GAME {state.game}", 52, 31, DARK, shadow=None)
        title = self.world.title_small
        HUD.draw_text(screen, title, L.SCREEN_W - HUD.text_width(title) - 8, 31, DARK, shadow=None)
        screen[15:44, 8:44] = (0, 0, 0)  # the item well: a sunken square
        bevel(screen, 8, 15, 43, 43, raised=False)
        if state.carried != 0x12:
            spr = self.held_icon(state.carried, frame_no)
            blit(screen, spr, 26 - spr.shape[1] / 2, 29 - spr.shape[0] / 2)

    def message_box(self, screen, lines, colours, top, portrait=None):
        """A message box: paper with a double border, its text centred, a portrait on the left if given."""
        text_w = max(HUD.text_width(line) for line in lines) + 32
        if portrait is not None and text_w + portrait.shape[1] + 12 > L.SCREEN_W - 8:
            portrait = None  # no room beside the text: the words matter more
        w = text_w + (portrait.shape[1] + 12 if portrait is not None else 0)
        h = 14 * len(lines) + 20
        if portrait is not None:
            h = max(h, portrait.shape[0] + 20)
        top = min(top, L.SCREEN_H - h - 2)  # always on screen, however many lines a world's words take
        x0 = (L.SCREEN_W - w) // 2
        screen[top:top + h, x0:x0 + w] = PAPER
        for inset in (0, 2):  # a double border
            screen[top + inset, x0 + inset:x0 + w - inset] = BLUE
            screen[top + h - 1 - inset, x0 + inset:x0 + w - inset] = BLUE
            screen[top + inset:top + h - inset, x0 + inset] = BLUE
            screen[top + inset:top + h - inset, x0 + w - 1 - inset] = BLUE
        text_x = x0 + 16
        if portrait is not None:
            blit(screen, portrait, x0 + 12, top + (h - portrait.shape[0]) // 2)
            text_x += portrait.shape[1] + 12
        for i, (text, colour) in enumerate(zip(lines, colours)):
            HUD.draw_text(screen, text, text_x, top + 10 + 14 * i, colour, shadow=None)

    def win_banner(self, screen, state, frame_no):
        who = self.cast.messenger(frame_no)
        who = None if who is None else self.adapt(who)
        self.message_box(screen, list(self.cast.win_lines), [INK] * len(self.cast.win_lines), 84, who)
        msg = "PRESS ENTER TO PLAY AGAIN"
        HUD.draw_text(screen, msg, (L.SCREEN_W - HUD.text_width(msg)) // 2, 160, PAPER, shadow=INK)

    def title_screen(self, state, frame_no):
        """A DOS prompt types the program's name; then the gold castle's room fades up from black - dim, its
        corners darker - with the cast's title figures standing small in the middle, under the title."""
        screen = np.zeros((L.SCREEN_H, L.SCREEN_W, 3), np.uint8)
        typed = "ADVENTUR"[:max(0, (frame_no - 20) // 6)]
        if frame_no < 90:  # the prompt, then the program starts
            cursor = "_" if (frame_no // 15) % 2 == 0 else " "
            HUD.draw_text(screen, f"C:\\GAMES>{typed}{cursor}", 8, 8, GREY, shadow=None)
            return screen
        light = round(min(1.0, (frame_no - 90) / 60) * 0.55, 2)  # fades up over a second, to a gloom
        key = ("title", self.world.key, light)
        if key not in self.sprite_cache:
            room = self.world.room(R.decode_room(R.load_rom(), 0x11)).astype(float)
            yy, xx = np.mgrid[0:L.ROOM_H, 0:L.ROOM_W]
            from_centre = np.hypot((xx - L.ROOM_W / 2) / (L.ROOM_W / 2), (yy - L.ROOM_H / 2) / (L.ROOM_H / 2))
            vignette = 1 - 0.55 * np.clip(from_centre - 0.35, 0, 1)  # the corners darker
            self.sprite_cache[key] = self.adapt_scenery((room * light * vignette[..., None]).astype(np.uint8))
        room = self.sprite_cache[key].copy()
        cast = [self.adapt(figure) for figure in self.cast.title_cast()]
        width = sum(figure.shape[1] for figure in cast) + 8 * (len(cast) - 1)
        x = L.ROOM_W // 2 - width // 2
        for figure in cast:  # standing in the middle of the room, small, together
            blit(room, figure, x, L.ROOM_H // 2 + 14 - figure.shape[0])
            x += figure.shape[1] + 8
        screen[L.HUD_H:L.HUD_H + L.ROOM_H, L.ROOM_X:L.ROOM_X + L.ROOM_W] = room
        self.menu_strip(screen)
        title, small = "ADVENTURE", self.world.title_small
        title_x = (L.SCREEN_W - HUD.text_width(title, 3)) // 2
        HUD.draw_text(screen, title, title_x, 40, PAPER, scale=3, shadow=INK)
        HUD.draw_text(screen, small, (L.SCREEN_W - HUD.text_width(small)) // 2, 68, PAPER, shadow=INK)
        lines = [f"SELECT GAME  < {state.game} >", "ENTER TO START" if (frame_no // 30) % 2 == 0 else "",
                 "BY WARREN ROBINETT 1980"]
        if self.world.footer:
            lines.append(self.world.footer)
        self.message_box(screen, lines, [INK, BLUE, DARK, DARK][:len(lines)], 168)
        return screen
