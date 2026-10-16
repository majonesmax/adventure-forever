"""Finding the player's Adventure ROM (never included - bring your own).

Looked for in order: a path given on the command line, roms/adventure.a26 next to the code (or bundled in a
personal app build), then the copy remembered in the player's folder. Failing all three, a small window asks
for the ROM to be dropped onto it - the same on every system - and keeps a copy for next time.
"""

import os
import shutil

import pygame

from app.fonts import mono
from engine import paths

ROM_SIZE = 4096  # Adventure is a 4 KB cartridge
REMEMBERED = os.path.join(paths.USER_DIR, "adventure.a26") if paths.FROZEN else paths.ROM


def check(path):
    """None if `path` looks like Adventure, else what's wrong with it."""
    if not os.path.isfile(path):
        return "That isn't a file."
    if os.path.getsize(path) != ROM_SIZE:
        return f"That's {os.path.getsize(path)} bytes - the Adventure ROM is exactly {ROM_SIZE}."
    return None


def remember(path):
    """Keep a copy in the player's folder, so it's found next time."""
    if os.path.abspath(path) != os.path.abspath(REMEMBERED):
        os.makedirs(paths.USER_DIR, exist_ok=True)
        shutil.copyfile(path, REMEMBERED)
    return REMEMBERED


def find_rom(given=None):
    """Path to the ROM, or None if the player closes the window without giving one."""
    if given:
        problem = check(given)
        if problem:
            print(f"{given}: {problem}", flush=True)
            return None
        return remember(given)
    for path in (paths.ROM, REMEMBERED):
        if os.path.exists(path):
            return path
    return ask()


def ask():
    """A window that waits for the ROM to be dragged onto it. Esc or closing it gives up."""
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((640, 360))
    pygame.display.set_caption(f"{paths.APP_NAME} - your Adventure ROM, please")
    big, small = mono(22, bold=True), mono(15)
    problem = None
    clock = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                pygame.display.quit()
                return None
            if e.type == pygame.DROPFILE:
                problem = check(e.file)
                if problem is None:
                    pygame.display.quit()
                    return remember(e.file)
        screen.fill((16, 16, 24))
        lines = [(big, "Drop your Adventure ROM here", (240, 200, 80)), (small, "", None),
                 (small, "Atari 2600 Adventure (1980): a 4 KB .a26 or .bin file.", (220, 220, 235)),
                 (small, "It's remembered after the first time.", (150, 150, 175)), (small, "", None),
                 (small, problem or "", (240, 110, 110)), (small, "", None),
                 (small, "Esc to quit", (110, 110, 135))]
        y = 70
        for font, text, colour in lines:
            if text:
                surf = font.render(text, True, colour)
                screen.blit(surf, ((640 - surf.get_width()) // 2, y))
            y += font.get_linesize() + 4
        pygame.draw.rect(screen, (90, 90, 120), (24, 24, 592, 312), 2, border_radius=10)
        pygame.display.flip()
        clock.tick(30)
