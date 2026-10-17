"""The "now showing" overlay: which look, cast and world are on screen, shown for a moment when one changes -
and, when the ROM isn't the version Adventure Forever is made for, what that means (engine/versions.py).

Drawn on the window only (like the REC dot) - never into a look's picture, so never into a recording.
Timed on the wall clock, so it fades even while the game is paused.
"""

import textwrap
import time

import pygame

from app.fonts import mono

SHOW_FOR = 2.5  # seconds fully visible
FADE_FOR = 0.6  # then fading out
ROWS = (("look", "LOOK"), ("cast", "CAST"), ("world", "WORLD"))
LABEL, TEXT, CHANGED, HINT = (150, 150, 175), (235, 235, 245), (248, 200, 72), (120, 120, 145)
WARN, WARN_TEXT = (240, 140, 60), (240, 220, 200)


class NowShowing:
    def __init__(self):
        self.font = mono(18, bold=True)
        self.small = mono(13)
        self.shown_at, self.changed, self.duration, self.note = None, None, SHOW_FOR, None
        self.warning = None  # (headline, [details]) about the ROM, shown under the names

    def show(self, changed=None, duration=SHOW_FOR, note=None):
        """Bring it up for `duration` seconds. changed: (pane, what) to highlight, e.g. ("PLAYING", "cast") or
        ("COMPARE", "world"); a change to the comparison shows both panes, whatever the view."""
        self.shown_at, self.changed, self.duration, self.note = time.perf_counter(), changed, duration, note

    def draw(self, screen, panes, centre_x, top=16):
        """Paint it over `screen`, centred on centre_x, if it's up. panes: [(title, look)] - [(None, look)]
        for the one look on screen, or the grid's ("PLAYING", look) and ("COMPARE", look)."""
        if self.shown_at is None:
            return
        age = time.perf_counter() - self.shown_at
        if age > self.duration + FADE_FOR:
            self.shown_at = None
            return
        alpha = 255 if age < self.duration else int(255 * (1 - (age - self.duration) / FADE_FOR))
        lines = []  # (font, label, label colour, text, text colour)
        if self.note:  # e.g. what was just added
            lines.append((self.small, "", CHANGED, self.note, CHANGED))
        for title, look in panes:
            if title:
                lines.append((self.small, "", LABEL, title, LABEL))
            names = {"look": look.platform_name, "cast": look.cast.name, "world": look.world.name}
            for key, label in ROWS:
                lit = self.changed == ((title or "PLAYING"), key)
                lines.append((self.font, label.ljust(6), LABEL, names[key], CHANGED if lit else TEXT))
        hint = ("L, C, W change yours - Shift+L, C, W the comparison - H: all keys" if len(panes) > 1
                else "L, C or W to change - I shows this - H: all keys")
        label_w = max(self.font.size(lbl)[0] for _, lbl, *_ in lines)
        width = max(label_w + font.size(text)[0] for font, _, _, text, _ in lines)
        width = max(width, self.small.size(hint)[0]) + 32
        heights = [font.get_linesize() + 2 for font, *_ in lines]
        height = sum(heights) + self.small.get_linesize() + 28
        box = pygame.Surface((width, height), pygame.SRCALPHA)
        box.fill((8, 8, 16, 215))
        pygame.draw.rect(box, (90, 90, 120, 255), box.get_rect(), 2, border_radius=6)
        y = 12
        for (font, label, label_c, text, text_c), h in zip(lines, heights):
            if label:
                box.blit(font.render(label, True, label_c), (16, y))
                box.blit(font.render(text, True, text_c), (16 + label_w, y))
            else:  # a pane's title
                box.blit(font.render(text, True, text_c), (16, y + 2))
            y += h
        box.blit(self.small.render(hint, True, HINT), (16, y + 6))
        box.set_alpha(alpha)
        screen.blit(box, (centre_x - width // 2, top))
        if self.warning:
            self.draw_warning(screen, centre_x, top + height + 8, alpha)

    def draw_warning(self, screen, centre_x, top, alpha):
        headline, details = self.warning
        lines = [(self.small, line, WARN) for line in textwrap.wrap(headline, 64)]
        for d in details:
            lines += [(self.small, line, WARN_TEXT) for line in textwrap.wrap(d, 64)]
        line_h = self.small.get_linesize()
        width = max(self.small.size(text)[0] for _, text, _ in lines) + 32
        box = pygame.Surface((width, len(lines) * line_h + 20), pygame.SRCALPHA)
        box.fill((24, 10, 4, 225))
        pygame.draw.rect(box, (*WARN, 255), box.get_rect(), 2, border_radius=6)
        for i, (font, text, colour) in enumerate(lines):
            box.blit(font.render(text, True, colour), (16, 10 + i * line_h))
        box.set_alpha(alpha)
        screen.blit(box, (centre_x - width // 2, top))
