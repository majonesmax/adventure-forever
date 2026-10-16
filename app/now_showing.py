"""The "now showing" overlay: which look, cast and world are on screen, shown for a moment when one changes.

Drawn on the window only (like the REC dot) - never into a look's picture, so never into a recording.
Timed on the wall clock, so it fades even while the game is paused.
"""

import time

import pygame

SHOW_FOR = 2.5  # seconds fully visible
FADE_FOR = 0.6  # then fading out
ROWS = (("look", "LOOK"), ("cast", "CAST"), ("world", "WORLD"))
LABEL, TEXT, CHANGED, HINT = (150, 150, 175), (235, 235, 245), (248, 200, 72), (120, 120, 145)


class NowShowing:
    def __init__(self):
        self.font = pygame.font.SysFont("menlo", 18, bold=True)
        self.small = pygame.font.SysFont("menlo", 13)
        self.shown_at, self.changed = None, None

    def show(self, changed=None):
        """Bring it up; `changed` ("look" / "cast" / "world") is highlighted."""
        self.shown_at, self.changed = time.perf_counter(), changed

    def draw(self, screen, look, centre_x, top=16):
        """Paint it over `screen`, centred on centre_x, if it's up. look: the look on screen."""
        if self.shown_at is None:
            return
        age = time.perf_counter() - self.shown_at
        if age > SHOW_FOR + FADE_FOR:
            self.shown_at = None
            return
        alpha = 255 if age < SHOW_FOR else int(255 * (1 - (age - SHOW_FOR) / FADE_FOR))
        names = {"look": look.platform_name, "cast": look.cast.name, "world": look.world.name}
        lines = [(self.font, label.ljust(6), LABEL, names[key], CHANGED if key == self.changed else TEXT)
                 for key, label in ROWS]
        hint = "press L, C or W to change, I to see this again"
        label_w = max(self.font.size(lbl)[0] for _, lbl, *_ in lines)
        width = max(label_w + self.font.size(name)[0] for *_, name, _ in lines)
        width = max(width, self.small.size(hint)[0]) + 32
        line_h = self.font.get_linesize() + 2
        height = 3 * line_h + self.small.get_linesize() + 28
        box = pygame.Surface((width, height), pygame.SRCALPHA)
        box.fill((8, 8, 16, 215))
        pygame.draw.rect(box, (90, 90, 120, 255), box.get_rect(), 2, border_radius=6)
        y = 12
        for font, label, label_c, name, name_c in lines:
            box.blit(font.render(label, True, label_c), (16, y))
            box.blit(font.render(name, True, name_c), (16 + label_w, y))
            y += line_h
        box.blit(self.small.render(hint, True, HINT), (16, y + 6))
        box.set_alpha(alpha)
        screen.blit(box, (centre_x - width // 2, top))
