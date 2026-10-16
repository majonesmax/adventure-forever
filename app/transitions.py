"""Classic 8-bit screen scrolls between rooms (presentation only).

When the room changes, the old and new screens slide past each other in the direction the hero left. The
caller stops calling retro_run while a scroll plays, so the game (dragons, bat, timers) simply waits:
gameplay timing is unchanged, the scroll just adds a pause.

Direction comes from how the hero's coordinates jump (the game wraps him to the opposite edge: leaving up
sets y = $0D, down y = $69, left x = $9E, right x = $03) or, for the castle gates, from the room pair.
Anything else (RESET, the game-number screen) gets no scroll - a plain cut, as before.
"""

import numpy as np

from engine import rooms as R
from shared.pixelart import blit

PX_PER_FRAME = {"up": 6, "down": 6, "left": 8, "right": 8}  # ~32 frames (half a second) either way


def scroll_direction(prev, st):
    """'up' / 'down' / 'left' / 'right', or None for a cut. prev, st: GameStates before/after."""
    a, b = prev.room_num, st.room_num
    if a == b or a == 0 or b == 0:
        return None
    for castle, (inside, _) in R.CASTLES.items():
        if (a, b) == (castle, inside):
            return "up"
        if (a, b) == (inside, castle):
            return "down"
    (x0, y0), (x1, y1) = prev.hero, st.hero
    dx, dy = x1 - x0, y1 - y0
    if abs(dy) >= 0x30 and abs(dy) >= abs(dx):
        return "up" if dy < 0 else "down"   # y counts up the screen: leaving the top wraps to a small y
    if abs(dx) >= 0x40:
        return "left" if dx > 0 else "right"
    return None


class Scroll:
    """Slides the room area of old_screen out and new_screen in. frame() -> the screen to show.
    Both screens are drawn WITHOUT the hero and his carried item (look.draw(..., actors=False)); those
    come in old_actors/new_actors (look.actors) and are drawn once, gliding from where they were in the old
    room to where they are in the new one - else the hero shows twice at the seam.
    rect: (x, y, w, h) of the room on the screen - the look's ROOM_RECT."""

    @classmethod
    def between(cls, look, before, after, frame_no):
        """The scroll from GameState `before` to `after` in `look`, or None when the change is a plain cut."""
        direction = scroll_direction(before, after)
        if direction is None:
            return None
        return cls(look.draw(before, frame_no, actors=False), look.draw(after, frame_no, actors=False), direction,
                   look.actors(before, frame_no), look.actors(after, frame_no), look.ROOM_RECT)

    def __init__(self, old_screen, new_screen, direction, old_actors, new_actors, rect):
        x0, y0, w, h = self.rect = rect
        self.old = old_screen[y0:y0 + h, x0:x0 + w]
        self.new = new_screen[y0:y0 + h, x0:x0 + w]
        self.base = new_screen.copy()  # status bar and borders from the new screen
        self.direction = direction
        self.span = h if direction in ("up", "down") else w
        self.offset = 0
        self.old_actors, self.new_actors = old_actors or {}, new_actors or {}

    @property
    def done(self):
        return self.offset >= self.span

    def frame(self):
        self.offset = min(self.offset + PX_PER_FRAME[self.direction], self.span)
        o, d = self.offset, self.direction
        if d == "up":      # new room comes in from the top
            strip = np.concatenate([self.new, self.old], axis=0)
            view = strip[self.span - o:2 * self.span - o]
        elif d == "down":  # from the bottom
            strip = np.concatenate([self.old, self.new], axis=0)
            view = strip[o:o + self.span]
        elif d == "left":  # from the left
            strip = np.concatenate([self.new, self.old], axis=1)
            view = strip[:, self.span - o:2 * self.span - o]
        else:              # from the right
            strip = np.concatenate([self.old, self.new], axis=1)
            view = strip[:, o:o + self.span]
        view = view.copy()
        # where each room's content sits right now (room-space shift of the old and the new room)
        sp = self.span
        old_shift, new_shift = {"up": ((0, o), (0, o - sp)), "down": ((0, -o), (0, sp - o)),
                                "left": ((o, 0), (o - sp, 0)), "right": ((-o, 0), (sp - o, 0))}[d]
        t = o / sp
        for key in self.new_actors:  # the look's drawing order (item under or over the hero)
            spr, nx, ny = self.new_actors[key]
            if key in self.old_actors:
                _, ox, oy = self.old_actors[key]
                x = (1 - t) * (ox + old_shift[0]) + t * (nx + new_shift[0])
                y = (1 - t) * (oy + old_shift[1]) + t * (ny + new_shift[1])
            else:  # only in the new room: ride along with it
                x, y = nx + new_shift[0], ny + new_shift[1]
            blit(view, spr, x, y)
        out = self.base.copy()
        x0, y0, w, h = self.rect
        out[y0:y0 + h, x0:x0 + w] = view
        return out
