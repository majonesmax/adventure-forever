"""Decode Adventure's objects straight out of the ROM: where each one's position lives, its states, graphics,
colour and size.

Object table at $FF44 (the game's "object list" descriptors), 9 bytes per object, numbered $00-$12:
  0-1 pointer to (room, x, y) - in RAM for things that move, in ROM for fixed ones (gates, author name)
  2-3 pointer to the current-state byte
  4-5 pointer to the state list: entries of (state, graphic lo, graphic hi); the game uses the FIRST entry
      whose state value is >= the current state (GetObjectState)
  6 colour, 7 B&W colour, 8 size (TIA NUSIZ: low bits 0 = normal, 5 = double width, 7 = quad width)
Graphic: bytes from the top down, ending at a 0 byte; bit 7 is the leftmost pixel; each byte covers 2 scan lines.

The RAM byte $9D (carried) and the game's own object loops use object number * 9.

Usage: python objects.py   -> prints every object's graphics as ASCII
"""

import os

from engine import rooms as R

OBJECT_TABLE = 0xFF44
N_OBJECTS = 0x13
NAMES = {0x00: "surround", 0x01: "gold gate", 0x02: "white gate", 0x03: "black gate", 0x04: "author name",
         0x05: "game number", 0x06: "red dragon", 0x07: "yellow dragon", 0x08: "green dragon", 0x09: "sword",
         0x0A: "bridge", 0x0B: "yellow key", 0x0C: "white key", 0x0D: "black key", 0x0E: "bat", 0x0F: "dot",
         0x10: "chalice", 0x11: "magnet", 0x12: "null"}
WIDTH_MULT = {0: 1, 5: 2, 7: 4}


def rd(rom, addr):
    return rom[addr & 0x0FFF]


def rd16(rom, addr):
    return rd(rom, addr) | rd(rom, addr + 1) << 8


def read_graphic(rom, addr, limit=256):  # the author's name is 96 bytes
    rows = []
    for i in range(limit):
        b = rd(rom, addr + i)
        if b == 0:
            break
        rows.append(b)
    return rows


def decode_object(rom, n):
    e = OBJECT_TABLE + 9 * n
    info, state_ptr, states_ptr = rd16(rom, e), rd16(rom, e + 2), rd16(rom, e + 4)
    states = []
    for i in range(16):  # the list is ordered by state value and ends with an $FF entry
        s, g = rd(rom, states_ptr + 3 * i), rd16(rom, states_ptr + 3 * i + 1)
        states.append((s, g))
        if s == 0xFF:
            break
    return {"num": n, "name": NAMES[n], "info": info, "state_ptr": state_ptr, "states": states,
            "graphics": {g: read_graphic(rom, g) for _, g in states},
            "colour": rd(rom, e + 6), "bw_colour": rd(rom, e + 7), "size": rd(rom, e + 8),
            "width": WIDTH_MULT.get(rd(rom, e + 8) & 7, 1)}


def decode_all(rom=None):
    rom = rom or R.load_rom()
    return [decode_object(rom, n) for n in range(N_OBJECTS)]


def graphic_for_state(obj, state):
    for s, g in obj["states"]:
        if state <= s:
            return obj["graphics"][g]
    return obj["graphics"][obj["states"][-1][1]]


class Reader:
    """Reads one object's live (room, x, y, state) out of the 128 RAM bytes - or ROM, for fixed objects."""

    def __init__(self, rom=None):
        self.rom = rom or R.load_rom()
        self.objects = decode_all(self.rom)

    def byte(self, ram, addr):
        return int(ram[addr - 0x80]) if 0x80 <= addr <= 0xFF else rd(self.rom, addr)

    def where(self, ram, n):
        o = self.objects[n]
        return tuple(self.byte(ram, o["info"] + i) for i in range(3))

    def state(self, ram, n):
        return self.byte(ram, self.objects[n]["state_ptr"])


def ascii_graphic(rows, width=1):
    return ["".join(("#" if (b >> (7 - i)) & 1 else ".") * width for i in range(8)) for b in rows]


if __name__ == "__main__":
    for o in decode_all():
        where = f"${o['info']:04X}" + (" (RAM)" if o["info"] < 0x100 else " (ROM)")
        print(f"${o['num']:02X} {o['name']:13s} pos {where}  state ${o['state_ptr']:04X}  colour ${o['colour']:02X}"
              f"  size ${o['size']:02X} (x{o['width']})  states " + " ".join(f"{s:02X}->{g:04X}" for s, g in o["states"]))
        if o["name"] in ("surround", "game number", "author name", "null"):
            continue
        shown = set()
        for _, g in o["states"]:
            if g in shown:
                continue
            shown.add(g)
            print(f"   graphic ${g:04X}:")
            for line in ascii_graphic(o["graphics"][g]):
                print("     " + line)
