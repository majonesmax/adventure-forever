"""The VGA look: Adventure redrawn as an early-90s PC adventure game (the Sierra / LucasArts era) - 256
colours chosen for the pictures, a grey menu strip, message boxes.

A RoomLook (looks/base.py): the shared machinery shows the world's rooms and places the cast; this module is
the VGA platform:
  rules     VGA's: 256 colours on screen, each one of 262,144 (64 levels a channel). Like the era's games,
            the 256 are picked for what's shown - one palette per cast and world (palette.py) - and every
            screen is drawn in them alone
  screens   a status bar with a grey menu strip, the place's name and what you carry; a DOS prompt before the
            title; the win in a message box
Its own pack is "classic"; it was made for moody, liminal worlds.
"""

import numpy as np

from engine import rooms as R
from engine.objects import Reader
from engine.state import GameState
from content.cast import Cast
from content.world import World
from content.pictures import FLASH
from looks.base import RoomLook
from shared import hud as HUD
from shared import layout as L
from shared.pixelart import blit
from looks.vga.palette import palette_for
from shared.types import Picture, Rgb

GREY, LIGHT, DARK, INK, PAPER = (170, 170, 170), (255, 255, 255), (85, 85, 85), (0, 0, 0), (232, 232, 220)
BAR_BG, BLUE = (16, 16, 24), (0, 0, 170)
GOLD_CASTLE = 0x11  # the room the title screen shows
TITLE_GLOOM = 0.55  # how lit the title's castle is once it has faded up


def title_room(world: World, light: float) -> Picture:
    """The gold castle's room as the title shows it: dimmed to `light`, its corners darker still."""
    room = world.room(R.decode_room(R.load_rom(), GOLD_CASTLE)).astype(float)
    yy, xx = np.mgrid[0:L.ROOM_H, 0:L.ROOM_W]
    from_centre = np.hypot((xx - L.ROOM_W / 2) / (L.ROOM_W / 2), (yy - L.ROOM_H / 2) / (L.ROOM_H / 2))
    vignette = 1 - 0.55 * np.clip(from_centre - 0.35, 0, 1)
    return (room * light * vignette[..., None]).astype(np.uint8)


def bevel(img: Picture, x0: int, y0: int, x1: int, y1: int, raised: bool = True) -> None:
    """A 3-D bevel, like the era's buttons and icon bars: light top-left, dark bottom-right (or the other way
    round, sunken)."""
    lit, shadowed = (LIGHT, DARK) if raised else (DARK, LIGHT)
    img[y0, x0:x1 + 1] = lit
    img[y0:y1 + 1, x0] = lit
    img[y1, x0:x1 + 1] = shadowed
    img[y0:y1 + 1, x1] = shadowed


class VgaLook(RoomLook):
    platform = "vga"
    platform_name = "VGA REMASTER"
    own_pack = "classic"

    def __init__(self, reader: Reader, cast: Cast, world: World):
        title = title_room(world, TITLE_GLOOM)  # the title is a scene of its own: its colours count too
        self.vga = palette_for(cast, world, own_colours=(PAPER, BAR_BG), scenes=[title])  # before adapting
        self.scenery = {}  # this look's own rooms: the palette depends on the cast too, not just the world
        super().__init__(reader, cast, world)

    # ---- the platform (the RoomLook methods) ----

    def adapt(self, sprite: Picture) -> Picture:
        """Sprites: the palette's nearest colours (the flashing marker is left for the flash)."""
        out = sprite.copy()
        keep = np.all(out[..., :3] == FLASH, axis=2)
        out[..., :3] = self.vga.show(out[..., :3])
        out[keep, :3] = FLASH
        return out

    def adapt_scenery(self, picture: Picture) -> Picture:
        """Rooms and gates: the palette's nearest colours."""
        out = picture.copy()
        out[..., :3] = self.vga.show(picture[..., :3])
        return out

    def draw(self, state: GameState, frame_no: int, actors: bool = True) -> Picture:
        """The screen, in the palette's 256 colours only - the torchlight and the status bar too."""
        return self.vga.show(super().draw(state, frame_no, actors))

    def menu_strip(self, screen: Picture) -> None:
        """The grey strip along the top, with menu words - a PC program's window, not a console's."""
        screen[0:11] = GREY
        screen[11] = DARK
        x = 6
        for word in ("ADVENTURE", "FILE", "GAME", "SOUND"):
            HUD.draw_text(screen, word, x, 2, INK, shadow=None)
            x += HUD.text_width(word) + 14

    def draw_hud(self, screen: Picture, state: GameState, frame_no: int) -> None:
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

    def message_box(self, screen: Picture, lines: list[str], colours: list[Rgb], top: int,
                    portrait: Picture | None = None) -> None:
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

    def win_banner(self, screen: Picture, state: GameState, frame_no: int) -> None:
        who = self.cast.messenger(frame_no)
        who = None if who is None else self.adapt(who)
        self.message_box(screen, list(self.cast.win_lines), [INK] * len(self.cast.win_lines), 84, who)
        msg = "PRESS ENTER TO PLAY AGAIN"
        HUD.draw_text(screen, msg, (L.SCREEN_W - HUD.text_width(msg)) // 2, 160, PAPER, shadow=INK)

    def title_screen(self, state: GameState, frame_no: int) -> Picture:
        """A DOS prompt types the program's name; then the gold castle's room fades up from black - dim, its
        corners darker - with the cast's title figures standing small in the middle, under the title."""
        screen = np.zeros((L.SCREEN_H, L.SCREEN_W, 3), np.uint8)
        typed = "ADVENTUR"[:max(0, (frame_no - 20) // 6)]
        if frame_no < 90:  # the prompt, then the program starts
            cursor = "_" if (frame_no // 15) % 2 == 0 else " "
            HUD.draw_text(screen, f"C:\\GAMES>{typed}{cursor}", 8, 8, GREY, shadow=None)
            return screen
        light = round(min(1.0, (frame_no - 90) / 60) * TITLE_GLOOM, 2)  # fades up over a second
        key = ("title", self.world.key, light)
        room = self.sprite_cache.get(key)
        if room is None:
            room = self.sprite_cache[key] = self.adapt_scenery(title_room(self.world, light))
        room = room.copy()
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
