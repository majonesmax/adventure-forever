"""Classic 8-bit screen scrolls between rooms (presentation only).

When the room changes, the old and new screens slide past each other in the direction the hero left. The
caller stops calling retro_run while a scroll plays, so the game (dragons, bat, timers) simply waits:
gameplay timing is unchanged, the scroll just adds a pause.

Direction comes from how the hero's coordinates jump (the game wraps him to the opposite edge: leaving up
sets y = $0D, down y = $69, left x = $9E, right x = $03) or, for the castle gates, from the room pair.
Anything else (RESET, the game-number screen) gets no scroll - a plain cut, as before.
"""

from typing import TYPE_CHECKING, Any

import numpy as np

from engine import rooms as R
from engine.state import GameState
from shared.pixelart import blit
from shared.types import Picture

if TYPE_CHECKING:   # only for the type checker
    from looks.base import RoomLook

PX_PER_FRAME = {"up": 6, "down": 6, "left": 8, "right": 8}  # ~32 frames (half a second) either way
Actors = dict[Any, tuple[Picture, float, float]]   # a look's actors: key -> (sprite, x, y) (look.actors)
Rect = tuple[int, int, int, int]                   # (x, y, width, height)


def scroll_direction(prev: GameState, state: GameState) -> str | None:
    """'up' / 'down' / 'left' / 'right', or None for a cut. prev, state: GameStates before/after."""
    room_before, room_after = prev.room_num, state.room_num
    if room_before == room_after or room_before == 0 or room_after == 0:  # room 0: the game-select screen
        return None
    for castle, (inside, _) in R.CASTLES.items():
        if (room_before, room_after) == (castle, inside):
            return "up"
        if (room_before, room_after) == (inside, castle):
            return "down"
    (x0, y0), (x1, y1) = prev.hero, state.hero
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
    def between(cls, look: "RoomLook", before: GameState, after: GameState, frame_no: int) -> "Scroll | None":
        """The scroll from GameState `before` to `after` in `look`, or None when the change is a plain cut."""
        direction = scroll_direction(before, after)
        if direction is None:
            return None
        old_screen = look.draw(before, frame_no, actors=False)
        new_screen = look.draw(after, frame_no, actors=False)
        old_actors, new_actors = look.actors(before, frame_no), look.actors(after, frame_no)
        return cls(old_screen, new_screen, direction, old_actors, new_actors, look.ROOM_RECT)

    def __init__(self, old_screen: Picture, new_screen: Picture, direction: str, old_actors: Actors | None,
                 new_actors: Actors | None, rect: Rect):
        x0, y0, w, h = self.rect = rect
        self.old = old_screen[y0:y0 + h, x0:x0 + w]
        self.new = new_screen[y0:y0 + h, x0:x0 + w]
        self.base = new_screen.copy()  # status bar and borders from the new screen
        self.direction = direction
        self.span = h if direction in ("up", "down") else w
        self.offset = 0
        self.old_actors, self.new_actors = old_actors or {}, new_actors or {}

    @property
    def done(self) -> bool:
        return self.offset >= self.span

    def frame(self) -> Picture:
        self.offset = min(self.offset + PX_PER_FRAME[self.direction], self.span)
        view = self.sliding_rooms()
        self.glide_actors(view)
        out = self.base.copy()
        x0, y0, w, h = self.rect
        out[y0:y0 + h, x0:x0 + w] = view
        return out

    def sliding_rooms(self) -> Picture:
        """The two rooms side by side (or one above the other), and the window onto them right now."""
        offset, span, direction = self.offset, self.span, self.direction
        if direction == "up":      # the new room comes in from the top
            strip = np.concatenate([self.new, self.old], axis=0)
            view = strip[span - offset:2 * span - offset]
        elif direction == "down":  # from the bottom
            strip = np.concatenate([self.old, self.new], axis=0)
            view = strip[offset:offset + span]
        elif direction == "left":  # from the left
            strip = np.concatenate([self.new, self.old], axis=1)
            view = strip[:, span - offset:2 * span - offset]
        else:                      # from the right
            strip = np.concatenate([self.old, self.new], axis=1)
            view = strip[:, offset:offset + span]
        return view.copy()

    def glide_actors(self, view: Picture) -> None:
        """The hero and his item, drawn once, moving from where they were in the old room to where they are
        in the new one as the rooms slide."""
        offset, span = self.offset, self.span
        # where each room's content sits right now (room-space shift of the old and the new room)
        shifts = {"up": ((0, offset), (0, offset - span)), "down": ((0, -offset), (0, span - offset)),
                  "left": ((offset, 0), (offset - span, 0)), "right": ((-offset, 0), (span - offset, 0))}
        old_shift, new_shift = shifts[self.direction]
        progress = offset / span  # 0 at the start, 1 when the new room has arrived
        for key in self.new_actors:  # the look's drawing order (item under or over the hero)
            sprite, new_x, new_y = self.new_actors[key]
            if key in self.old_actors:
                _, old_x, old_y = self.old_actors[key]
                x = (1 - progress) * (old_x + old_shift[0]) + progress * (new_x + new_shift[0])
                y = (1 - progress) * (old_y + old_shift[1]) + progress * (new_y + new_shift[1])
            else:  # only in the new room: ride along with it
                x, y = new_x + new_shift[0], new_y + new_shift[1]
            blit(view, sprite, x, y)
