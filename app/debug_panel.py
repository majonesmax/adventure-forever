"""The INTERNALS quadrant of play.py's grid view: the game's whole state - 128 bytes of 6502 RAM - live, what
those bytes mean, and a log of events read from how they change. Real data only: the libretro core doesn't
expose the CPU's program counter, so there is no (fake) running disassembly.

  RAM dump   $80-$FF, a byte flashes when it changes and cools over ~1 s (HOT -> GREEN), zeros dim.
  Decoded    room, hero, carried object, the three dragons, the bat, the gates, sound, random seed.
  Event log  room changes, pick-ups / drops, dragon attacks / deaths / meals, the bat's thefts, gates,
             sound events ($E0 type when the $DF counter starts), game start / win.
"""

from typing import Callable

import numpy as np
import pygame

from app.fonts import mono
from engine import objects as O
from engine import ram_map as M
from engine.state import GameState
from shared.types import RamBytes, RamView, Rgb

BACKGROUND, GREEN, DIM, HOT = (4, 10, 6), (90, 230, 130), (40, 96, 56), (255, 255, 190)
AMBER, GREY, RED = (255, 190, 80), (120, 150, 128), (255, 110, 100)
SOUNDS = {0: "game over", 1: "roar", 2: "eaten", 3: "dragon dies", 4: "drop", 5: "pickup"}
DRAGONS = (("RHINDLE", M.RED_DRAGON), ("YORGLE", M.YELLOW_DRAGON), ("GRUNDLE", M.GREEN_DRAGON))
GATES = (("gold", 0xC8), ("white", 0xC9), ("black", 0xCA))
GATE_CLOSED = 0x1C
COOL = 60  # frames for a changed byte to cool from HOT to GREEN
LogLine = tuple[int, str, Rgb]   # (frame, what happened, its colour)

# a famous 1980s wagon under the old hex marker for dead memory: shown while a dragon has eaten the hero
# (its state byte = $02) - until RESET revives him
WAGON = """
..............XXXXXXXXXXXXXXX.........................
...........XXX...............XXX......................
.........XX.....................XX....................
........X...X.....X.....X.....X...X...................
........X...X.....X.....X.....X...X...............X.X.
........X...X.....X.....X.....X...X..............XXXX.
........X...X.....X.....X.....X...X.....XXXXXXXXXXXXXX
........XXXXXXXXXXXXXXXXXXXXXXXXXXX....XXXXXXXXXXXX.XX
........X.........................X...XXXXXXXXXXXXX...
........XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX....
.........XXXX...............XXXX.......XXXXXXXXXXX....
........X.XX.X.............X.XX.X......X.X.....X.X....
........XX..XX.............XX..XX......X.X.....X.X....
........X.XX.X.............X.XX.X......X.X.....X.X....
.........XXXX...............XXXX......................
"""


def dragon_word(state: int) -> str:
    """A dragon's state byte, in a word."""
    return {0: "normal", 1: "dead", 2: "ate hero"}.get(state, "ROAR")


def obj_name(object_number: int) -> str:
    return "-" if object_number == 0x12 else O.NAMES.get(object_number, f"?{object_number:02X}")


def byte(ram: RamBytes, addr: int) -> int:
    """The byte at a 2600 address ($80-$FF) in a 128-byte RAM copy."""
    return int(ram[addr - 0x80])


class DebugPanel:
    def __init__(self, size: tuple[int, int] = (512, 480)):
        self.size = size
        self.font = mono(13)
        self.cw, self.ch = self.font.size("0")[0], self.font.get_linesize()
        self.prev: RamView | None = None
        self.changed_at = np.full(128, -10_000)
        self.log: list[LogLine] = []
        self.frame_no = 0
        # listener(text): gets every event too (recorder.py writes them to log.jsonl)
        self.listener: Callable[[str], None] | None = None
        self.scan: pygame.Surface | None = None   # the scanlines, made once

    def event(self, text: str, colour: Rgb = GREEN) -> None:
        self.log = (self.log + [(self.frame_no, text, colour)])[-9:]
        if self.listener is not None:
            self.listener(text)

    def update(self, state: GameState | None, ram: RamBytes, frame_no: int) -> None:
        """Call once per emulated frame (also when the grid isn't showing, so the log has history)."""
        copied: RamView = np.asarray(ram, np.uint8).copy()
        self.frame_no = frame_no
        if self.prev is not None:
            self.changed_at[copied != self.prev] = frame_no
            self.diff_events(self.prev, copied)
        self.prev = copied

    def diff_events(self, before: RamView, after: RamView) -> None:
        """Events, read from how the RAM changed since the last frame."""
        if byte(before, M.ROOM) != byte(after, M.ROOM):
            self.event(f"ROOM ${byte(before, M.ROOM):02X} -> ${byte(after, M.ROOM):02X}")
        self.carry_events(before, after)
        self.dragon_events(before, after)
        if byte(before, 0xD0) != byte(after, 0xD0):  # the bat's carry byte - format not decoded yet: raw
            self.event(f"BAT carry ${byte(before, 0xD0):02X} -> ${byte(after, 0xD0):02X}", AMBER)
        for name, addr in GATES:
            was_closed, is_closed = byte(before, addr) == GATE_CLOSED, byte(after, addr) == GATE_CLOSED
            if was_closed != is_closed:
                self.event(f"{name} gate {'closes' if is_closed else 'opens'}")
        if byte(before, 0xDF) == 0 and byte(after, 0xDF) != 0:  # a sound starts counting down
            sound = byte(after, 0xE0)
            self.event(f"SOUND  {SOUNDS.get(sound, sound)}", GREY)
        if byte(before, M.GAME_ACTIVE) != byte(after, M.GAME_ACTIVE):
            # $DE is only ever set by a win (being eaten leaves it 0); RESET clears it
            started = byte(after, M.GAME_ACTIVE) == 0
            self.event("GAME START" if started else "WIN - THE CHALICE IS HOME!", AMBER)

    def carry_events(self, before: RamView, after: RamView) -> None:
        carried_before, carried_after = byte(before, M.CARRIED) // 9, byte(after, M.CARRIED) // 9
        if carried_before == carried_after:
            return
        if carried_before != 0x12:
            self.event(f"DROP   {obj_name(carried_before)}", GREY)
        if carried_after != 0x12:
            self.event(f"PICKUP {obj_name(carried_after)}", AMBER)

    def dragon_events(self, before: RamView, after: RamView) -> None:
        for name, addr in DRAGONS:
            state_before, state_after = byte(before, addr + 4), byte(after, addr + 4)
            if state_before != state_after and dragon_word(state_before) != dragon_word(state_after):
                colour = RED if state_after >= 2 else AMBER if state_after == 1 else GREEN
                self.event(f"{name} {dragon_word(state_before)} -> {dragon_word(state_after)}", colour)
            moved_room = byte(before, addr) != byte(after, addr)
            if moved_room and byte(after, addr) == byte(after, M.ROOM):
                self.event(f"{name} enters the room", RED)

    def text(self, surf: pygame.Surface, column: int, row: int, words: str, colour: Rgb) -> None:
        """Words at a text position: column and row in characters."""
        surf.blit(self.font.render(words, True, colour), (8 + column * self.cw, 6 + row * self.ch))

    def eaten_by(self) -> str | None:
        """Name of the dragon that has swallowed the hero, or None."""
        if self.prev is None:
            return None
        for name, addr in DRAGONS:
            if int(self.prev[addr + 4 - 0x80]) == 2:
                return name
        return None

    def deadbeef(self, surf: pygame.Surface, who: str) -> None:
        """The wagon and 0xDEADBEEF, the old marker for dead memory (he was eaten - the footnote admits
        it)."""
        centre_x = self.size[0] // 2
        rows = WAGON.strip("\n").split("\n")
        dot = 7  # px per character of the drawing
        x0, y0 = centre_x - len(rows[0]) * dot // 2, 70
        bob = (self.frame_no // 20) % 2  # the wagon rocks a little (not its wheels)
        for y, row in enumerate(rows):
            for x, char in enumerate(row):
                if char == "X":
                    lift = bob if y < 10 else 0
                    pygame.draw.rect(surf, GREEN, (x0 + x * dot, y0 + y * dot + lift, dot, dot))
        ground = y0 + len(rows) * dot + 4
        pygame.draw.line(surf, DIM, (20, ground), (self.size[0] - 20, ground), 2)
        big = mono(22, bold=True)
        lines = [("0xDEADBEEF", big, GREEN)]
        y = y0 + len(rows) * dot + 40
        for text, font, colour in lines:
            img = font.render(text, True, colour)
            surf.blit(img, (centre_x - img.get_width() // 2, y))
            y += img.get_height() + 6
        y += 24
        for text, colour in ((f"(actually: eaten by {who})", GREY),
                             ("", GREY),
                             ("PRESS ENTER TO TRY AGAIN" if (self.frame_no // 30) % 2 == 0 else "", AMBER)):
            img = self.font.render(text, True, colour)
            surf.blit(img, (centre_x - img.get_width() // 2, y))
            y += self.ch + 4

    def draw(self, surf: pygame.Surface, state: GameState) -> None:
        surf.fill(BACKGROUND)
        if self.prev is None:
            return
        who = self.eaten_by()
        if who:
            self.deadbeef(surf, who)
            surf.blit(self.scanlines(), (0, 0))
            return
        self.text(surf, 0, 0, f"INTERNALS  6502 RAM $80-$FF   frame {self.frame_no:06d}", AMBER)
        self.draw_ram(surf)
        self.draw_decoded(surf, state, top=11)
        self.text(surf, 0, 20, "EVENT LOG " + "-" * 44, GREY)
        for i, (when, message, colour) in enumerate(reversed(self.log)):
            self.text(surf, 0, 21 + i, f"{when:06d}  {message}", colour if i < 3 else DIM)
        surf.blit(self.scanlines(), (0, 0))

    def draw_ram(self, surf: pygame.Surface) -> None:
        """The 128 bytes, 16 a row: a changed byte glows and cools over COOL frames; zeros dim."""
        ram = self.prev
        if ram is None:
            return
        for row in range(8):
            self.text(surf, 0, 2 + row, f"${0x80 + row * 16:02X}", GREY)
            for column in range(16):
                i = row * 16 + column
                age = self.frame_no - self.changed_at[i]
                x, y = 8 + (5 + column * 3) * self.cw, 6 + (2 + row) * self.ch
                if age < COOL:  # just changed: a glowing cell that cools off
                    cooled = age / COOL
                    mixed = [int(hot * (1 - cooled) + cool * cooled) for hot, cool in zip(HOT, GREEN)]
                    red, green, blue = mixed
                    colour: Rgb = (red, green, blue)
                    glow = tuple(int(channel * (1 - cooled) * 0.45) for channel in (60, 255, 120))
                    pygame.draw.rect(surf, glow, (x - 3, y, self.cw * 2 + 6, self.ch))
                else:
                    colour = DIM if ram[i] == 0 else GREEN
                self.text(surf, 5 + column * 3, 2 + row, f"{ram[i]:02X}", colour)

    def draw_decoded(self, surf: pygame.Surface, state: GameState, top: int) -> None:
        """What the bytes mean: the room and game, the hero, the dragons, the bat, the gates, the sound."""
        ram = self.prev
        if ram is None:
            return

        def value(addr: int) -> int:
            return byte(ram, addr)
        playing = "playing" if value(M.GAME_ACTIVE) == 0 else "ended"
        room_name = state.room["name"][:22]
        game = value(M.LEVEL) // 2 + 1
        self.text(surf, 0, top, f"ROOM ${state.room_num:02X} {room_name:22s} GAME {game} {playing}", GREEN)
        hero_x, hero_y = state.hero
        carrying = obj_name(state.carried)
        self.text(surf, 0, top + 1, f"HERO  x ${hero_x:02X} y ${hero_y:02X}    CARRY {carrying}", GREEN)
        for i, (name, addr) in enumerate(DRAGONS):
            dragon_state = value(addr + 4)
            here = value(addr) == state.room_num
            colour = RED if here and dragon_state >= 2 else AMBER if here else GREEN
            where = f"room ${value(addr):02X}  ${value(addr + 1):02X},${value(addr + 2):02X}"
            self.text(surf, 0, top + 2 + i,
                      f"{name:8s} {where}  state ${dragon_state:02X} {dragon_word(dragon_state)}", colour)
        bat_where = f"room ${value(M.BAT):02X}  ${value(M.BAT + 1):02X},${value(M.BAT + 2):02X}"
        self.text(surf, 0, top + 5, f"BAT      {bat_where}  carry byte ${value(0xD0):02X}", GREEN)
        gates = []
        for name, addr in GATES:
            gate = "shut" if value(addr) == GATE_CLOSED else f"${value(addr):02X}"
            gates.append(f"{name} {gate}")
        self.text(surf, 0, top + 6, f"GATES    {'  '.join(gates)}", GREEN)
        sound = value(0xE0)
        self.text(surf, 0, top + 7, f"SOUND    type ${sound:02X} {SOUNDS.get(sound, '?'):11s} count "
                                    f"${value(0xDF):02X}   SEED ${value(M.RANDOM):02X}", GREEN)

    def scanlines(self) -> pygame.Surface:
        """CRT look: every other line darkened (cached)."""
        if self.scan is None:
            self.scan = pygame.Surface(self.size, pygame.SRCALPHA)
            for yy in range(0, self.size[1], 2):
                pygame.draw.line(self.scan, (0, 0, 0, 70), (0, yy), (self.size[0], yy))
        return self.scan
