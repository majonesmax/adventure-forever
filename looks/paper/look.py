"""The paper look: Adventure drawn in crayon in a spiral-bound sketchbook - a box of crayons, the paper's
grain showing through the wax, handwriting, and an index card for messages.

A RoomLook (looks/base.py): the shared machinery shows the world's rooms and places the cast; this module is
the paper platform:
  rules     a box of 17 crayons: every colour becomes the nearest crayon, and a colour close to the paper is
            left as bare paper. In rooms and gates the crayon is waxy - the paper's grain shows through it -
            and the room's biggest colour (usually the floor) is coloured in lightly, the way a whole page is.
            Sprites keep solid crayon colours, so they stay readable
  dark      a dark room away from the torch is blank paper: what the hero can't see isn't drawn yet
  screens   a sketchbook's spiral binding over the status bar, handwritten words; the title is written and the
            castle drawn in while you watch; messages on a ruled index card
Its own pack is "classic"; it was made for drawn worlds.
"""

import numpy as np

from engine import rooms as R
from content.pictures import FLASH
from looks.base import RoomLook
from shared import hud as HUD
from shared import layout as L
from shared.pixelart import blit

PAPER = np.array((246, 240, 226), float)
CRAYONS = np.array([  # the box: one row per crayon (peach among them, for faces)
    (34, 30, 36), (120, 78, 52), (204, 48, 52), (240, 128, 48), (250, 210, 60), (170, 204, 70),
    (60, 150, 72), (40, 150, 150), (110, 180, 228), (44, 84, 180), (112, 64, 168), (196, 70, 140),
    (244, 150, 170), (250, 200, 160), (212, 170, 120), (150, 148, 150), (254, 254, 250)], float)
VIOLET, GRAPHITE, CARD = (112, 64, 168), (70, 68, 74), (252, 252, 246)
RULE, MARGIN = (150, 190, 226), (226, 120, 120)  # an index card's blue lines and red header line
FULL, LIGHT_HAND = 0.88, 0.42  # how much crayon a pixel gets: pressed in, and coloured in lightly


def grain(h, w, seed=7):
    """The paper's tooth, 0..1 per pixel: a fixed noise smeared along the crayon's diagonal strokes, so the
    paper shows through in short streaks rather than speckles."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, (h + 8, w + 8))
    smeared = sum(np.roll(np.roll(noise, k, 0), 2 * k, 1) for k in range(-3, 4))  # along a 1:2 diagonal
    smeared = smeared[4:h + 4, 4:w + 4]
    smeared = (smeared - smeared.min()) / (smeared.max() - smeared.min())  # 0..1
    return np.clip((smeared - 0.22) * 2.2, 0, 1)  # more contrast: most of it fully covered


TOOTH = grain(L.SCREEN_H, L.SCREEN_W)


def crayon_index(rgb):
    """RGB (..., 3) -> the nearest crayon's row in CRAYONS, or -1 for bare paper."""
    pal = np.vstack([CRAYONS, PAPER[None]])
    distance = ((rgb[..., None, :].astype(float) - pal) ** 2).sum(-1)
    nearest = distance.argmin(-1)
    nearest[nearest == len(CRAYONS)] = -1  # the last row was the paper
    return nearest


def wax(rgb, idx, pressure, tooth):
    """Crayon `idx` laid on paper with `pressure` (0..1 per pixel), the paper's tooth showing through."""
    cover = (pressure * (0.35 + 0.65 * tooth))[..., None]
    colour = CRAYONS[np.maximum(idx, 0)]
    out = PAPER * (1 - cover) + colour * cover
    out[idx < 0] = PAPER
    return out.astype(np.uint8)


def spiral(screen):
    """The sketchbook's binding along the top: wire loops through punched holes."""
    for x in range(10, L.SCREEN_W - 4, 14):
        screen[6:9, x:x + 4] = (90, 86, 82)                    # the hole
        screen[1:7, x + 1:x + 3] = (150, 150, 158)             # the wire over the top
        screen[1, x:x + 4] = (190, 190, 198)


def scrawl(screen, text, x, y, colour, scale=1, seed=0):
    """Handwritten: the pixel font with each letter a little up or down."""
    for i, letter in enumerate(text):
        raised = (i * 7 + seed * 3 + len(text)) % 5 == 0  # a fixed pattern, so the words don't jiggle
        lowered = (i * 5 + seed) % 7 == 0
        dy = int(raised) - int(lowered)
        letter_x = x + HUD.text_width(text[:i], scale)
        HUD.draw_text(screen, letter, letter_x, y + dy * scale, colour, scale=scale, shadow=None)


def index_card(screen, lines, colours, top, portrait=None):
    """A ruled index card - a red margin line, blue rules, the words written on the lines."""
    text_w = max(HUD.text_width(line) for line in lines) + 32
    if portrait is not None and text_w + portrait.shape[1] + 12 > L.SCREEN_W - 8:
        portrait = None  # no room beside the words: the words matter more
    w = min(L.SCREEN_W - 8, text_w + (portrait.shape[1] + 12 if portrait is not None else 0))
    h = 14 * len(lines) + 18
    if portrait is not None:
        h = max(h, portrait.shape[0] + 18)
    top = min(top, L.SCREEN_H - h - 3)  # always on screen, however many lines a world's words take
    x0 = (L.SCREEN_W - w) // 2
    screen[top + 2:top + h + 2, x0 + 2:x0 + w + 2] = (screen[top + 2:top + h + 2, x0 + 2:x0 + w + 2] * 0.8)
    screen[top:top + h, x0:x0 + w] = CARD
    for rule_y in range(top + 21, top + h - 2, 14):
        screen[rule_y, x0 + 2:x0 + w - 2] = RULE
    screen[top + 7, x0 + 2:x0 + w - 2] = MARGIN               # the card's red header line
    text_x = x0 + 16
    if portrait is not None:
        blit(screen, portrait, x0 + 10, top + (h - portrait.shape[0]) // 2)
        text_x += portrait.shape[1] + 10
    for i, (text, colour) in enumerate(zip(lines, colours)):
        scrawl(screen, text, text_x, top + 12 + 14 * i, colour, seed=i)


class PaperLook(RoomLook):
    platform = "paper"
    platform_name = "PAPER & CRAYON"
    own_pack = "classic"

    # ---- the platform (the RoomLook methods) ----

    def adapt(self, sprite):
        """Sprites: the nearest crayons, solid (the flashing marker is left for the flash); near-paper colours
        become the paper."""
        out = sprite.copy()
        keep = np.all(out[..., :3] == FLASH, axis=2)
        idx = crayon_index(out[..., :3])
        out[..., :3] = np.where((idx < 0)[..., None], PAPER, CRAYONS[np.maximum(idx, 0)]).astype(np.uint8)
        out[keep, :3] = FLASH
        return out

    def adapt_scenery(self, picture):
        """Rooms and gates: waxy crayon on paper, the paper's tooth showing through; the biggest colour in a
        room coloured in lightly."""
        out = picture.copy()
        h, w = picture.shape[:2]
        idx = crayon_index(picture[..., :3])
        pressure = np.full((h, w), FULL)
        if picture.shape[2] == 3:  # a room: its main colour (usually the floor) coloured in lightly
            counts = np.bincount(idx[idx >= 0].ravel(), minlength=len(CRAYONS))
            if counts.max() > 0.35 * h * w:
                pressure[idx == counts.argmax()] = LIGHT_HAND
        out[..., :3] = wax(picture[..., :3], idx, pressure, TOOTH[:h, :w])
        return out

    def unlit(self, room, light):
        """Away from the torch the page is blank: the drawing fades to paper, not to black."""
        light = light[..., None]
        return (room * light + PAPER * (1 - light)).astype(np.uint8)

    def draw_hud(self, screen, state, frame_no):
        screen[:L.HUD_H] = PAPER
        screen[:, :L.ROOM_X] = PAPER                            # the page's margins beside the room
        screen[:, L.ROOM_X + L.ROOM_W:] = PAPER
        spiral(screen)
        screen[L.HUD_H - 2, :] = (220, 212, 196)                # the page's edge above the room
        place = self.world.area_name(state.room_num)
        scrawl(screen, place, 52, 18, VIOLET, seed=state.room_num)
        scrawl(screen, f"GAME {state.game}", 52, 31, GRAPHITE)
        title = self.world.title_small
        scrawl(screen, title, L.SCREEN_W - HUD.text_width(title) - 8, 31, GRAPHITE, seed=3)
        self.doodle_ring(screen, 26, 29, 14)
        if state.carried != 0x12:
            spr = self.held_icon(state.carried, frame_no)
            blit(screen, spr, 26 - spr.shape[1] / 2, 29 - spr.shape[0] / 2)

    @staticmethod
    def doodle_ring(screen, centre_x, centre_y, radius):
        """A circle drawn round twice by hand - where the carried item goes."""
        for lap, (lap_radius, start) in enumerate(((radius, 0.0), (radius + 0.8, 0.5))):
            for angle in np.linspace(start, start + 2 * np.pi * 0.95, 160):  # not quite closed
                wobble = 0.7 * np.sin(3 * angle + lap)
                x = int(round(centre_x + (lap_radius + wobble) * np.cos(angle)))
                y = int(round(centre_y + (lap_radius + wobble) * 0.9 * np.sin(angle)))
                if 0 <= y < L.HUD_H and 0 <= x < L.SCREEN_W:
                    screen[y, x] = GRAPHITE

    def win_banner(self, screen, state, frame_no):
        who = self.cast.messenger(frame_no)
        who = None if who is None else self.adapt(who)
        lines = list(self.cast.win_lines)
        index_card(screen, lines, [VIOLET] + [GRAPHITE] * (len(lines) - 1), 84, who)
        msg = "PRESS ENTER TO PLAY AGAIN"
        x = (L.SCREEN_W - HUD.text_width(msg)) // 2
        screen[158:170, x - 4:x + HUD.text_width(msg) + 4] = CARD
        scrawl(screen, msg, x, 160, GRAPHITE)

    def title_screen(self, state, frame_no):
        """A blank page: ADVENTURE is written a letter at a time, then the gold castle's room is drawn in from
        left to right, the cast's title figures in the middle, and an index card says what to press."""
        screen = np.empty((L.SCREEN_H, L.SCREEN_W, 3), np.uint8)
        screen[:] = PAPER
        spiral(screen)
        title, small = "ADVENTURE", self.world.title_small
        written = title[:max(0, frame_no // 5)]
        scrawl(screen, written, (L.SCREEN_W - HUD.text_width(title, 3)) // 2, 12, VIOLET, scale=3)
        if frame_no < 50:
            return screen
        scrawl(screen, small, (L.SCREEN_W - HUD.text_width(small)) // 2, 37, GRAPHITE, seed=2)
        key = ("title", self.world.key)
        if key not in self.sprite_cache:
            self.sprite_cache[key] = self.adapt_scenery(self.world.room(R.decode_room(R.load_rom(), 0x11)))
        room = self.sprite_cache[key].copy()
        cast = [self.adapt(figure) for figure in self.cast.title_cast()]
        width = sum(figure.shape[1] for figure in cast) + 8 * (len(cast) - 1)
        x = L.ROOM_W // 2 - width // 2
        for figure in cast:  # standing in the middle of the room, together
            blit(room, figure, x, L.ROOM_H // 2 + 14 - figure.shape[0])
            x += figure.shape[1] + 8
        drawn = int(min(1.0, (frame_no - 50) / 60) * L.ROOM_W)  # drawn in, left to right, over a second
        page = screen[L.HUD_H:L.HUD_H + L.ROOM_H, L.ROOM_X:L.ROOM_X + L.ROOM_W]
        page[:, :drawn] = room[:, :drawn]
        if frame_no < 110:
            return screen
        lines = [f"SELECT GAME  < {state.game} >", "ENTER TO START" if (frame_no // 30) % 2 == 0 else "",
                 "BY WARREN ROBINETT 1980"]
        if self.world.footer:
            lines.append(self.world.footer)
        index_card(screen, lines, [GRAPHITE, VIOLET, GRAPHITE, GRAPHITE][:len(lines)], 160)
        return screen
