"""The first tool of the project: play Adventure in the raw emulator with a live RAM panel beside it -
handy for watching what a byte does. (The game window's grid view has a fancier panel: app/debug_panel.py.)

Usage: python tools/ram_viewer.py [rom]
Keys: arrows + space = joystick, Tab = GAME SELECT, Enter = RESET, R = RAM panel on/off, P = pause, Esc = quit.
"""

import os
import sys

import numpy as np
import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, when run as a script
from app.fonts import mono
from engine import paths
from engine.emulator import (JOY_B, JOY_DOWN, JOY_LEFT, JOY_RIGHT, JOY_SELECT, JOY_START, JOY_UP, AudioOut,
                             Core)
from shared.types import RamView

class RamPanel:
    """128 bytes as a 16x8 hex grid; changed bytes flash yellow and fade over ~1 s."""

    def __init__(self, font: pygame.font.Font):
        self.font: pygame.font.Font = font
        self.prev: RamView | None = None
        self.heat = np.zeros(128)

    def update(self, ram: RamView) -> None:
        cur = ram.copy()
        if self.prev is not None:
            self.heat[cur != self.prev] = 1.0
        self.heat *= 0.95
        self.prev = cur

    def draw(self, surf: pygame.Surface, x0: int, y0: int) -> None:
        cw, ch = self.font.size("00 ")[0], self.font.get_linesize()
        for row in range(8):
            surf.blit(self.font.render(f"${0x80 + row * 16:02X}", True, (120, 120, 140)), (x0, y0 + (row + 1) * ch))
        for col in range(16):
            surf.blit(self.font.render(f"{col:X}", True, (120, 120, 140)), (x0 + 40 + col * cw, y0))
        for i, v in enumerate(self.prev if self.prev is not None else []):
            h = self.heat[i]
            colour = (int(160 + 95 * h), int(160 + 95 * h), int(160 * (1 - h)))
            surf.blit(self.font.render(f"{v:02X}", True, colour),
                      (x0 + 40 + (i % 16) * cw, y0 + (i // 16 + 1) * ch))


def main() -> None:
    rom = sys.argv[1] if len(sys.argv) > 1 else paths.ROM
    core = Core()
    core.load(os.path.abspath(rom))
    ram = core.ram
    assert ram is not None   # load() made the live view of the RAM
    av = core.av_info()
    fps, rate = av.timing.fps, int(av.timing.sample_rate) or 31400
    gw, gh = av.geometry.base_width, av.geometry.base_height
    print(f"core: {gw}x{gh} @ {fps:.3f} fps, audio {rate} Hz, pixel format {core.pixel_format}", flush=True)
    pygame.display.init()  # not pygame.init(): that also opens pygame's own audio mixer, a 2nd stream on the card
    pygame.font.init()
    audio = AudioOut(rate)
    scale, panel_w = 3, 420
    screen = pygame.display.set_mode((gw * scale + panel_w, gh * scale))  # the core already outputs 2600 pixels doubled (160 -> 320)
    pygame.display.set_caption("Adventure - Stella libretro core (spike)")
    font = mono(15)
    panel, show_panel, paused = RamPanel(font), True, False
    joymap = {pygame.K_UP: JOY_UP, pygame.K_DOWN: JOY_DOWN, pygame.K_LEFT: JOY_LEFT, pygame.K_RIGHT: JOY_RIGHT,
              pygame.K_SPACE: JOY_B, pygame.K_TAB: JOY_SELECT, pygame.K_RETURN: JOY_START}
    snap_dir, n = os.environ.get("SPIKE_SNAP"), 0
    clock = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                return
            if e.type in (pygame.KEYDOWN, pygame.KEYUP):
                down = e.type == pygame.KEYDOWN
                if e.key in joymap:
                    (core.joy.add if down else core.joy.discard)(joymap[e.key])
                elif down and e.key == pygame.K_r:
                    show_panel = not show_panel
                elif down and e.key == pygame.K_p:
                    paused = not paused
        if not paused:
            core.run()
            audio.push(core.take_audio())
            panel.update(ram)
            n += 1
        screen.fill((16, 16, 24))
        if core.frame is not None:
            surf = pygame.surfarray.make_surface(core.frame.transpose(1, 0, 2))
            screen.blit(pygame.transform.scale(surf, (gw * scale, gh * scale)), (0, 0))
        if show_panel:
            panel.draw(screen, gw * scale + 16, 16)
        pygame.display.flip()
        if snap_dir and n % 120 == 0 and core.frame is not None:
            from PIL import Image
            Image.fromarray(core.frame).save(os.path.join(snap_dir, f"spike_{n:05d}.png"))
            np.save(os.path.join(snap_dir, f"ram_{n:05d}.npy"), ram.copy())
        clock.tick(fps)


if __name__ == "__main__":
    main()
