"""The SNES look: Adventure redrawn as a 16-bit Super Nintendo game.

A RoomLook (looks/base.py): the shared machinery shows the world's rooms and places the cast; this module is
the SNES platform:
  rules     the cast's sprites get soft outlines (each dark edge pixel becomes a dark shade of the colour
            beside it) and at most 15 colours, in the SNES's 15-bit colour (outline.py)
  screens   the status bar with the place's name in the world's colour, the title screen with the gold
            castle and the cast's title cast, the win banner with the cast's messenger in a speech bubble
Its own pack is "pbj" (packs/pbj): PBJ and friends in the candy, ice and fire kingdoms.
"""

import numpy as np
from PIL import Image

from engine import rooms as R
from looks.base import BRIDGE, RoomLook
from looks.snes.outline import recolour_outline
from shared import hud as HUD
from shared import layout as L
from shared.palettes import NES, flash_colour
from shared.pixelart import blit, snes_rgb

BAR = (16, 8, 40)


class SnesLook(RoomLook):
    platform = "snes"
    platform_name = "SNES REMASTER"
    own_pack = "pbj"

    def __init__(self, reader, cast, world):
        super().__init__(reader, cast, world)
        rom = R.load_rom()
        for n in range(1, R.N_ROOMS):  # paint every room up front: no hitch on first entry
            self.room_image(R.decode_room(rom, n))

    # ---- the platform (the RoomLook methods) ----

    def adapt(self, sprite):
        """The SNES's 15-bit colour, then soft outlines and at most 15 colours (outline.py)."""
        return recolour_outline(self.adapt_scenery(sprite))

    def adapt_scenery(self, picture):
        """15-bit colour: 32 levels a channel (snes_rgb), for rooms and gates too."""
        out = picture.copy()
        out[..., :3] = snes_rgb(out[..., :3])
        return out

    def carried_on_top(self, n):
        """The hero is far bigger than the 2600's (a 4x8 square): held items go over him so they don't vanish.
        Drawn exactly where the game has them - a nudge to clear his body made swords miss where they
        looked like they hit (the game hit-tests the real positions). The bridge stays under him."""
        return n != BRIDGE

    def logo(self, screen, y, scale, colour, shadow):
        """ADVENTURE with the world's small word: after it (HUD, scale 2) or under its last letter (title, 3)."""
        title, small = "ADVENTURE", self.world.title_small
        if scale == 2:  # the HUD: centre ADVENTURE + the small word in the space right of the item box
            total = HUD.text_width(title, 2) - 4 + HUD.text_width(small)
            x = 48 + (L.SCREEN_W - 48 - total) // 2
        else:
            x = (L.SCREEN_W - HUD.text_width(title, scale)) // 2
        HUD.draw_text(screen, title, x, y, colour, scale=scale, shadow=shadow)
        if scale == 2:  # bottoms aligned (a 5x7 glyph x2 is 14 px tall)
            HUD.draw_text(screen, small, x + HUD.text_width(title, 2) - 4, y + 7, (240, 240, 240))
        else:  # right-aligned with the last letter (5 px glyph x3 = 15)
            right = x + HUD.text_width(title, scale) - 24 + 15
            HUD.draw_text(screen, small, right - (HUD.text_width(small) - 3), y + 24, (240, 240, 240), shadow=shadow)

    def draw_hud(self, screen, st, frame_no):
        screen[:L.HUD_H] = BAR
        colour = self.world.colour(st.room_num)
        HUD.draw_text(screen, "ITEM", 12, 5, (232, 232, 240))
        HUD.frame_box(screen, 8, 15, 43, 43, colour)
        self.logo(screen, 6, 2, colour, (0, 0, 0))
        label = self.world.area_name(st.room_num)
        HUD.draw_text(screen, label, (L.SCREEN_W - HUD.text_width(label)) // 2 + 12, 26, (240, 240, 240))
        game = f"GAME {st.game}"
        HUD.draw_text(screen, game, (L.SCREEN_W - HUD.text_width(game)) // 2 + 12, 37, (152, 152, 176))
        if st.carried != 0x12:
            spr = self.held_icon(st.carried, frame_no)
            blit(screen, spr, 26 - spr.shape[1] / 2, 29 - spr.shape[0] / 2)

    def win_splash(self, st, frame_no):
        return None  # the messenger's speech bubble stays up (win_banner)

    def win_banner(self, screen, st, frame_no):
        """The cast's messenger (x2) delivers the news in a speech bubble."""
        y0, y1 = 72, 160
        screen[y0:y1, 12:244] = BAR
        colour = NES[flash_colour(frame_no, every=4)]
        HUD.frame_box(screen, 12, y0, 243, y1 - 1, colour)
        who = self.cast.messenger(frame_no)
        if who is not None:
            who = self.adapt(who).repeat(2, axis=0).repeat(2, axis=1)
            blit(screen, who, 44 - who.shape[1] / 2, y0 + 8 + max(0, (46 - who.shape[0]) // 2))
        # speech bubble: white, dark line, cut corners, a tail pointing at the messenger
        bx0, bx1, by0, by1, ink = 76, 236, y0 + 8, y0 + 50, (24, 32, 48)
        screen[by0:by1, bx0:bx1] = (248, 248, 248)
        HUD.frame_box(screen, bx0, by0, bx1 - 1, by1 - 1, ink)
        for i in range(5):  # tail
            screen[by0 + 14 + i, bx0 - 5 + i:bx0 + 1] = (248, 248, 248)
            screen[by0 + 14 + i, bx0 - 6 + i] = ink
        screen[by0 + 19, bx0 - 1:bx0 + 1] = ink
        accent = (200, 56, 120)
        for i, text in enumerate(self.cast.win_lines):
            HUD.draw_text(screen, text, (bx0 + bx1 - HUD.text_width(text)) // 2, by0 + 6 + 12 * i,
                          ink if i == 0 else accent, shadow=None)
        msg = "PRESS ENTER TO PLAY AGAIN"
        HUD.draw_text(screen, msg, (L.SCREEN_W - HUD.text_width(msg)) // 2, y0 + 64, colour)

    def title_screen(self, st, frame_no):
        screen = np.zeros((L.SCREEN_H, L.SCREEN_W, 3), np.uint8)
        screen[:] = BAR
        pink = self.world.colour(0x11)
        self.logo(screen, 14, 3, pink, (104, 32, 72))
        # the gold castle at half size, the cast's title cast (x2) in front of its gate
        castle = Image.fromarray(self.room_image(R.decode_room(R.load_rom(), 0x11))).resize((120, 96), Image.BOX)
        x0, y0 = (L.SCREEN_W - 120) // 2, 46
        screen[y0:y0 + 96, x0:x0 + 120] = np.array(castle)
        HUD.frame_box(screen, x0 - 1, y0 - 1, x0 + 120, y0 + 96, pink)
        cast = [self.adapt(c).repeat(2, axis=0).repeat(2, axis=1) for c in self.cast.title_cast()]
        width = sum(c.shape[1] for c in cast) + 6 * (len(cast) - 1)
        x = L.SCREEN_W // 2 - width // 2
        for c in cast:
            blit(screen, c, x, y0 + 96 - c.shape[0] + 14)
            x += c.shape[1] + 6
        game = st.game
        lines = [(f"SELECT GAME  < {game} >", 160, (240, 240, 240))]
        if (frame_no // 30) % 2 == 0:
            lines.append(("PRESS ENTER TO START", 178, pink))
        lines += [("TAB CHANGES THE GAME", 194, (152, 152, 176)),
                  ("BY WARREN ROBINETT 1980", 214, (152, 152, 176)),
                  (self.world.footer, 226, (152, 152, 176))]
        for text, y, c in lines:
            HUD.draw_text(screen, text, (L.SCREEN_W - HUD.text_width(text)) // 2, y, c)
        return screen
