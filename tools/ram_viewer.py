"""The first tool of the project: play Adventure in the raw emulator with a live RAM panel beside it -
handy for watching what a byte does. (The game window's grid view has a fancier panel: app/debug_panel.py.)

Usage: python tools/ram_viewer.py [rom]
Keys: arrows + space = joystick, Tab = GAME SELECT, Enter = RESET, R = RAM panel on/off, P = pause,
      Esc = quit.
"""

import os
import sys

import numpy as np
import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, as a script
from app.fonts import mono
from engine import paths
from engine.emulator import (JOY_B, JOY_DOWN, JOY_LEFT, JOY_RIGHT, JOY_SELECT, JOY_START, JOY_UP, AudioOut,
                             Core)
from shared.types import RamView

JOYSTICK = {pygame.K_UP: JOY_UP, pygame.K_DOWN: JOY_DOWN, pygame.K_LEFT: JOY_LEFT, pygame.K_RIGHT: JOY_RIGHT,
            pygame.K_SPACE: JOY_B, pygame.K_TAB: JOY_SELECT, pygame.K_RETURN: JOY_START}
LABEL_GREY = (120, 120, 140)


class RamPanel:
    """128 bytes as a 16x8 hex grid; changed bytes flash yellow and fade over ~1 s."""

    def __init__(self, font: pygame.font.Font):
        self.font: pygame.font.Font = font
        self.prev: RamView | None = None
        self.heat = np.zeros(128)

    def update(self, ram: RamView) -> None:
        current = ram.copy()
        if self.prev is not None:
            self.heat[current != self.prev] = 1.0
        self.heat *= 0.95
        self.prev = current

    def draw(self, surf: pygame.Surface, x0: int, y0: int) -> None:
        cell_w, cell_h = self.font.size("00 ")[0], self.font.get_linesize()
        for row in range(8):
            row_label = self.font.render(f"${0x80 + row * 16:02X}", True, LABEL_GREY)
            surf.blit(row_label, (x0, y0 + (row + 1) * cell_h))
        for col in range(16):
            surf.blit(self.font.render(f"{col:X}", True, LABEL_GREY), (x0 + 40 + col * cell_w, y0))
        for i, value in enumerate(self.prev if self.prev is not None else []):
            heat = self.heat[i]
            colour = (int(160 + 95 * heat), int(160 + 95 * heat), int(160 * (1 - heat)))
            surf.blit(self.font.render(f"{value:02X}", True, colour),
                      (x0 + 40 + (i % 16) * cell_w, y0 + (i // 16 + 1) * cell_h))


class Controls:
    """What the keys have switched: the panel, pause - and whether to quit."""

    def __init__(self) -> None:
        self.show_panel, self.paused, self.quit = True, False, False

    def handle(self, core: Core) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                self.quit = True
                return
            if event.type not in (pygame.KEYDOWN, pygame.KEYUP):
                continue
            down = event.type == pygame.KEYDOWN
            if event.key in JOYSTICK:
                (core.joy.add if down else core.joy.discard)(JOYSTICK[event.key])
            elif down and event.key == pygame.K_r:
                self.show_panel = not self.show_panel
            elif down and event.key == pygame.K_p:
                self.paused = not self.paused


def snapshot(snap_dir: str, frame_count: int, core: Core, ram: RamView) -> None:
    """SPIKE_SNAP: every 120 frames, the frame as a PNG and the RAM as a .npy."""
    if frame_count % 120 != 0 or core.frame is None:
        return
    from PIL import Image
    Image.fromarray(core.frame).save(os.path.join(snap_dir, f"spike_{frame_count:05d}.png"))
    np.save(os.path.join(snap_dir, f"ram_{frame_count:05d}.npy"), ram.copy())


def main() -> None:
    rom = sys.argv[1] if len(sys.argv) > 1 else paths.ROM
    core = Core()
    core.load(os.path.abspath(rom))
    ram = core.ram
    assert ram is not None   # load() made the live view of the RAM
    av_info = core.av_info()
    fps, rate = av_info.timing.fps, int(av_info.timing.sample_rate) or 31400
    game_w, game_h = av_info.geometry.base_width, av_info.geometry.base_height
    print(f"core: {game_w}x{game_h} @ {fps:.3f} fps, audio {rate} Hz, pixel format {core.pixel_format}",
          flush=True)
    pygame.display.init()  # not pygame.init(): that also opens pygame's own audio mixer, a 2nd stream
    pygame.font.init()
    audio = AudioOut(rate)
    scale, panel_w = 3, 420
    # the core already outputs 2600 pixels doubled (160 -> 320)
    screen = pygame.display.set_mode((game_w * scale + panel_w, game_h * scale))
    pygame.display.set_caption("Adventure - Stella libretro core (spike)")
    panel, controls = RamPanel(mono(15)), Controls()
    snap_dir, frame_count = os.environ.get("SPIKE_SNAP"), 0
    clock = pygame.time.Clock()
    while True:
        controls.handle(core)
        if controls.quit:
            return
        if not controls.paused:
            core.run()
            audio.push(core.take_audio())
            panel.update(ram)
            frame_count += 1
        screen.fill((16, 16, 24))
        if core.frame is not None:
            surf = pygame.surfarray.make_surface(core.frame.transpose(1, 0, 2))
            screen.blit(pygame.transform.scale(surf, (game_w * scale, game_h * scale)), (0, 0))
        if controls.show_panel:
            panel.draw(screen, game_w * scale + 16, 16)
        pygame.display.flip()
        if snap_dir:
            snapshot(snap_dir, frame_count, core, ram)
        clock.tick(fps)


if __name__ == "__main__":
    main()
