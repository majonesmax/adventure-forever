"""The INTERNALS quadrant of play.py's grid view: the game's whole state - 128 bytes of 6502 RAM - live, what
those bytes mean, and a log of events read from how they change. Real data only: the libretro core doesn't
expose the CPU's program counter, so there is no (fake) running disassembly.

  RAM dump   $80-$FF, a byte flashes when it changes and cools over ~1 s (HOT -> GREEN), zeros dim.
  Decoded    room, hero, carried object, the three dragons, the bat, the gates, sound, random seed.
  Event log  room changes, pick-ups / drops, dragon attacks / deaths / meals, the bat's thefts, gates,
             sound events ($E0 type when the $DF counter starts), game start / win.
"""

import numpy as np
import pygame

from app.fonts import mono
from engine import objects as O
from engine import ram_map as M

BG, GREEN, DIM, HOT, AMBER, GREY, RED = ((4, 10, 6), (90, 230, 130), (40, 96, 56), (255, 255, 190),
                                         (255, 190, 80), (120, 150, 128), (255, 110, 100))
SOUNDS = {0: "game over", 1: "roar", 2: "eaten", 3: "dragon dies", 4: "drop", 5: "pickup"}
DRAGONS = (("RHINDLE", M.RED_DRAGON), ("YORGLE", M.YELLOW_DRAGON), ("GRUNDLE", M.GREEN_DRAGON))
GATES = (("gold", 0xC8), ("white", 0xC9), ("black", 0xCA))
GATE_CLOSED = 0x1C
COOL = 60  # frames for a changed byte to cool from HOT to GREEN

# a famous 1980s game-over line: shown while a dragon has eaten the hero (its state byte = $02) - until RESET revives him
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


def dragon_word(state):
    return "dead" if state == 1 else "normal" if state == 0 else "ate hero" if state == 2 else "ROAR"


def obj_name(n):
    return "-" if n == 0x12 else O.NAMES.get(n, f"?{n:02X}")


class DebugPanel:
    def __init__(self, size=(512, 480)):
        self.size = size
        self.font = mono(13)
        self.cw, self.ch = self.font.size("0")[0], self.font.get_linesize()
        self.prev = None
        self.changed_at = np.full(128, -10_000)
        self.log = []
        self.frame_no = 0
        self.listener = None  # listener(text): gets every event too (recorder.py writes them to log.jsonl)

    def event(self, text, colour=GREEN):
        self.log = (self.log + [(self.frame_no, text, colour)])[-9:]
        if self.listener is not None:
            self.listener(text)

    def update(self, st, ram, frame_no):
        """Call once per emulated frame (also when the grid isn't showing, so the log has history)."""
        ram = np.asarray(ram, np.uint8).copy()
        self.frame_no = frame_no
        if self.prev is not None:
            self.changed_at[ram != self.prev] = frame_no
            self.diff_events(self.prev, ram)
        self.prev = ram

    def diff_events(self, a, b):
        r = lambda m, addr: int(m[addr - 0x80])
        if r(a, 0x8A) != r(b, 0x8A):
            self.event(f"ROOM ${r(a, 0x8A):02X} -> ${r(b, 0x8A):02X}")
        ca, cb = r(a, M.CARRIED) // 9, r(b, M.CARRIED) // 9
        if ca != cb:
            if ca != 0x12:
                self.event(f"DROP   {obj_name(ca)}", GREY)
            if cb != 0x12:
                self.event(f"PICKUP {obj_name(cb)}", AMBER)
        for name, addr in DRAGONS:
            sa, sb = r(a, addr + 4), r(b, addr + 4)
            if sa != sb and dragon_word(sa) != dragon_word(sb):
                colour = RED if sb >= 2 else AMBER if sb == 1 else GREEN
                self.event(f"{name} {dragon_word(sa)} -> {dragon_word(sb)}", colour)
            if r(a, addr) != r(b, addr) and r(b, addr) == r(b, 0x8A):
                self.event(f"{name} enters the room", RED)
        if r(a, 0xD0) != r(b, 0xD0):  # the bat's carry byte - format not decoded yet, so shown raw
            self.event(f"BAT carry ${r(a, 0xD0):02X} -> ${r(b, 0xD0):02X}", AMBER)
        for name, addr in GATES:
            ga, gb = r(a, addr), r(b, addr)
            if (ga == GATE_CLOSED) != (gb == GATE_CLOSED):
                self.event(f"{name} gate {'closes' if gb == GATE_CLOSED else 'opens'}")
        if r(a, 0xDF) == 0 and r(b, 0xDF) != 0:
            self.event(f"SOUND  {SOUNDS.get(r(b, 0xE0), r(b, 0xE0))}", GREY)
        if r(a, M.GAME_ACTIVE) != r(b, M.GAME_ACTIVE):
            # $DE is only ever set by a win (being eaten leaves it 0); RESET clears it
            self.event("GAME START" if r(b, M.GAME_ACTIVE) == 0 else "WIN - THE CHALICE IS HOME!", AMBER)

    def text(self, surf, x, y, s, colour):
        surf.blit(self.font.render(s, True, colour), (8 + x * self.cw, 6 + y * self.ch))

    def eaten_by(self):
        """Name of the dragon that has swallowed the hero, or None."""
        if self.prev is None:
            return None
        for name, addr in DRAGONS:
            if int(self.prev[addr + 4 - 0x80]) == 2:
                return name
        return None

    def dysentery(self, surf, who):
        """Green-screen tribute: the hero 'died of dysentery' (he was eaten - the footnote admits it)."""
        cx = self.size[0] // 2
        rows = WAGON.strip("\n").split("\n")
        px = 7
        x0, y0 = cx - len(rows[0]) * px // 2, 70
        bob = (self.frame_no // 20) % 2  # the wagon rocks a little
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch == "X":
                    pygame.draw.rect(surf, GREEN, (x0 + x * px, y0 + y * px + (bob if y < 10 else 0), px, px))
        pygame.draw.line(surf, DIM, (20, y0 + len(rows) * px + 4), (self.size[0] - 20, y0 + len(rows) * px + 4), 2)
        big = mono(22, bold=True)
        lines = [("YOU HAVE DIED", big, GREEN), ("OF DYSENTERY.", big, GREEN)]
        y = y0 + len(rows) * px + 40
        for text, font, colour in lines:
            img = font.render(text, True, colour)
            surf.blit(img, (cx - img.get_width() // 2, y))
            y += img.get_height() + 6
        y += 24
        for text, colour in ((f"(actually: eaten by {who})", GREY),
                             ("", GREY),
                             ("PRESS ENTER TO TRY AGAIN" if (self.frame_no // 30) % 2 == 0 else "", AMBER)):
            img = self.font.render(text, True, colour)
            surf.blit(img, (cx - img.get_width() // 2, y))
            y += self.ch + 4

    def draw(self, surf, st):
        surf.fill(BG)
        if self.prev is None:
            return
        who = self.eaten_by()
        if who:
            self.dysentery(surf, who)
            surf.blit(self.scanlines(), (0, 0))
            return
        ram, f = self.prev, self.frame_no
        self.text(surf, 0, 0, f"INTERNALS  6502 RAM $80-$FF   frame {f:06d}", AMBER)
        for row in range(8):
            self.text(surf, 0, 2 + row, f"${0x80 + row * 16:02X}", GREY)
            for col in range(16):
                i = row * 16 + col
                age = f - self.changed_at[i]
                x, yy = 8 + (5 + col * 3) * self.cw, 6 + (2 + row) * self.ch
                if age < COOL:  # just changed: a glowing cell that cools off
                    t = age / COOL
                    colour = tuple(int(h * (1 - t) + g * t) for h, g in zip(HOT, GREEN))
                    glow = tuple(int(c * (1 - t) * 0.45) for c in (60, 255, 120))
                    pygame.draw.rect(surf, glow, (x - 3, yy, self.cw * 2 + 6, self.ch))
                else:
                    colour = DIM if ram[i] == 0 else GREEN
                self.text(surf, 5 + col * 3, 2 + row, f"{ram[i]:02X}", colour)
        r = lambda addr: int(ram[addr - 0x80])
        y = 11
        state = "playing" if r(M.GAME_ACTIVE) == 0 else "ended"
        self.text(surf, 0, y, f"ROOM ${st.room_num:02X} {st.room['name'][:22]:22s} GAME {r(M.LEVEL) // 2 + 1} {state}", GREEN)
        self.text(surf, 0, y + 1, f"HERO  x ${st.hero[0]:02X} y ${st.hero[1]:02X}    CARRY {obj_name(st.carried)}", GREEN)
        for i, (name, addr) in enumerate(DRAGONS):
            here = r(addr) == st.room_num
            self.text(surf, 0, y + 2 + i, f"{name:8s} room ${r(addr):02X}  ${r(addr + 1):02X},${r(addr + 2):02X}  "
                                          f"state ${r(addr + 4):02X} {dragon_word(r(addr + 4))}",
                      RED if here and r(addr + 4) >= 2 else AMBER if here else GREEN)
        self.text(surf, 0, y + 5, f"BAT      room ${r(M.BAT):02X}  ${r(M.BAT + 1):02X},${r(M.BAT + 2):02X}  "
                                  f"carry byte ${r(0xD0):02X}", GREEN)
        gates = "  ".join(f"{n} {'shut' if r(a) == GATE_CLOSED else f'${r(a):02X}'}" for n, a in GATES)
        self.text(surf, 0, y + 6, f"GATES    {gates}", GREEN)
        self.text(surf, 0, y + 7, f"SOUND    type ${r(0xE0):02X} {SOUNDS.get(r(0xE0), '?'):11s} count ${r(0xDF):02X}"
                                  f"   SEED ${r(M.RANDOM):02X}", GREEN)
        self.text(surf, 0, y + 9, "EVENT LOG " + "-" * 44, GREY)
        for i, (when, msg, colour) in enumerate(reversed(self.log)):
            self.text(surf, 0, y + 10 + i, f"{when:06d}  {msg}", colour if i < 3 else DIM)
        surf.blit(self.scanlines(), (0, 0))

    def scanlines(self):
        """CRT look: every other line darkened (cached)."""
        if getattr(self, "_scan", None) is None:
            self._scan = pygame.Surface(self.size, pygame.SRCALPHA)
            for yy in range(0, self.size[1], 2):
                pygame.draw.line(self._scan, (0, 0, 0, 70), (0, yy), (self.size[0], yy))
        return self._scan
