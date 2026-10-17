"""The help panel (H): every key, from app/controls.py, over the picture. The game waits while it's up.
Drawn on the window only (like the overlays), never into a recording."""

import pygame

from app import controls
from app.fonts import mono

TITLE, SECTION, KEY, TEXT, HINT = (248, 200, 72), (150, 150, 175), (248, 200, 72), (235, 235, 245), (120, 120, 145)


class HelpPanel:
    def __init__(self):
        self.title, self.font, self.small = mono(20, bold=True), mono(15), mono(13)
        self.open = False

    def toggle(self):
        self.open = not self.open

    def draw(self, screen):
        """The panel centred on `screen`, two columns of sections, if it's open."""
        if not self.open:
            return
        key_w = max(self.font.size(keys)[0] for keys in controls.labels()) + 18
        text_w = max(self.font.size(what)[0] for _, rows in controls.SECTIONS for _, what, _ in rows)
        col_w, line_h = key_w + text_w, self.font.get_linesize() + 3
        half = (len(controls.SECTIONS) + 1) // 2
        columns = [controls.SECTIONS[:half], controls.SECTIONS[half:]]
        col_h = [sum(line_h * (len(rows) + 1) + 8 for _, rows in col) for col in columns]
        width, height = 2 * col_w + 3 * 24, max(col_h) + 90
        k = min(1.0, (screen.get_width() - 16) / width, (screen.get_height() - 16) / height)
        panel = pygame.Surface((width, height))  # solid: the picture behind it shouldn't show through
        panel.fill((8, 8, 16))
        pygame.draw.rect(panel, (90, 90, 120), panel.get_rect(), 2)
        title = self.title.render("ADVENTURE FOREVER - KEYS", True, TITLE)
        panel.blit(title, ((width - title.get_width()) // 2, 16))
        for c, col in enumerate(columns):
            x, y = 24 + c * (col_w + 24), 56
            for name, rows in col:
                panel.blit(self.small.render(name, True, SECTION), (x, y + 2))
                y += line_h
                for keys, what, _ in rows:
                    panel.blit(self.font.render(keys, True, KEY), (x, y))
                    panel.blit(self.font.render(what, True, TEXT), (x + key_w, y))
                    y += line_h
                y += 8
        hint = self.small.render("H or Esc closes this.  To add a pack, drop its folder or .zip on the window.",
                                 True, HINT)
        panel.blit(hint, ((width - hint.get_width()) // 2, height - 26))
        if k < 1.0:
            panel = pygame.transform.smoothscale(panel, (int(width * k), int(height * k)))
        screen.blit(panel, ((screen.get_width() - panel.get_width()) // 2,
                            (screen.get_height() - panel.get_height()) // 2))
