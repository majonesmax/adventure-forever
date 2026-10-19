"""Decode Adventure's objects straight out of the ROM: where each one's position lives, its states, graphics,
colour and size.

Object table at $FF44 (the game's "object list" descriptors), 9 bytes per object, numbered $00-$12:
  0-1 pointer to (room, x, y) - in RAM for things that move, in ROM for fixed ones (gates, author name)
  2-3 pointer to the current-state byte
  4-5 pointer to the state list: entries of (state, graphic lo, graphic hi); the game uses the FIRST entry
      whose state value is >= the current state (GetObjectState)
  6 colour, 7 B&W colour, 8 size (TIA NUSIZ: low bits 0 = normal, 5 = double width, 7 = quad width)
Graphic: bytes from the top down, ending at a 0 byte; bit 7 is the leftmost pixel; each byte covers 2 scan
lines.

The RAM byte $9D (carried) and the game's own object loops use object number * 9.

Usage: python objects.py   -> prints every object's graphics as ASCII
"""

import os
from typing import Any

from engine import rooms as R
from shared.types import RamBytes

GameObject = dict[str, Any]   # an object's table entry, decoded: num, name, info, states, graphics...

OBJECT_TABLE = 0xFF44
N_OBJECTS = 0x13
NAMES = {0x00: "surround", 0x01: "gold gate", 0x02: "white gate", 0x03: "black gate", 0x04: "author name",
         0x05: "game number", 0x06: "red dragon", 0x07: "yellow dragon", 0x08: "green dragon", 0x09: "sword",
         0x0A: "bridge", 0x0B: "yellow key", 0x0C: "white key", 0x0D: "black key", 0x0E: "bat", 0x0F: "dot",
         0x10: "chalice", 0x11: "magnet", 0x12: "null"}
WIDTH_MULT = {0: 1, 5: 2, 7: 4}


def rd(rom: bytes, addr: int) -> int:
    return rom[addr & 0x0FFF]


def rd16(rom: bytes, addr: int) -> int:
    return rd(rom, addr) | rd(rom, addr + 1) << 8


def read_graphic(rom: bytes, addr: int, limit: int = 256) -> list[int]:  # the author's name is 96 bytes
    rows: list[int] = []
    for i in range(limit):
        row = rd(rom, addr + i)
        if row == 0:  # a 0 byte ends the graphic
            break
        rows.append(row)
    return rows


def decode_object(rom: bytes, object_number: int) -> GameObject:
    entry = OBJECT_TABLE + 9 * object_number  # 9 bytes an object
    info, state_ptr, states_ptr = rd16(rom, entry), rd16(rom, entry + 2), rd16(rom, entry + 4)
    states: list[tuple[int, int]] = []  # (the highest state value this graphic is for, the graphic's address)
    for i in range(16):  # the list is ordered by state value and ends with an $FF entry
        up_to_state = rd(rom, states_ptr + 3 * i)
        graphic_addr = rd16(rom, states_ptr + 3 * i + 1)
        states.append((up_to_state, graphic_addr))
        if up_to_state == 0xFF:
            break
    size = rd(rom, entry + 8)
    return {"num": object_number, "name": NAMES[object_number], "info": info, "state_ptr": state_ptr,
            "states": states, "graphics": {addr: read_graphic(rom, addr) for _, addr in states},
            "colour": rd(rom, entry + 6), "bw_colour": rd(rom, entry + 7), "size": size,
            "width": WIDTH_MULT.get(size & 7, 1)}


def decode_all(rom: bytes | None = None) -> list[GameObject]:
    rom = rom or R.load_rom()
    return [decode_object(rom, object_number) for object_number in range(N_OBJECTS)]


def graphic_for_state(obj: GameObject, state: int) -> list[int]:
    """The object's graphic (rows of bytes) for a state value: the first entry whose limit reaches it."""
    for up_to_state, graphic_addr in obj["states"]:
        if state <= up_to_state:
            return obj["graphics"][graphic_addr]
    last_graphic = obj["states"][-1][1]
    return obj["graphics"][last_graphic]


class Reader:
    """Reads one object's live (room, x, y, state) out of the 128 RAM bytes - or ROM, for fixed objects."""

    def __init__(self, rom: bytes | None = None):
        self.rom: bytes = rom or R.load_rom()
        self.objects: list[GameObject] = decode_all(self.rom)

    def byte(self, ram: RamBytes, addr: int) -> int:
        return int(ram[addr - 0x80]) if 0x80 <= addr <= 0xFF else rd(self.rom, addr)

    def where(self, ram: RamBytes, object_number: int) -> tuple[int, int, int]:
        """(room, x, y)"""
        info = self.objects[object_number]["info"]  # where its three bytes are
        return self.byte(ram, info), self.byte(ram, info + 1), self.byte(ram, info + 2)

    def state(self, ram: RamBytes, object_number: int) -> int:
        return self.byte(ram, self.objects[object_number]["state_ptr"])


def ascii_graphic(rows: list[int], width: int = 1) -> list[str]:
    """A graphic as text: "#" for each set bit, left (bit 7) to right."""
    lines = []
    for row in rows:
        bits = [(row >> (7 - i)) & 1 for i in range(8)]
        lines.append("".join(("#" if bit else ".") * width for bit in bits))
    return lines


if __name__ == "__main__":
    for obj in decode_all():
        where = f"${obj['info']:04X}" + (" (RAM)" if obj["info"] < 0x100 else " (ROM)")
        state_list = " ".join(f"{up_to:02X}->{addr:04X}" for up_to, addr in obj["states"])
        print(f"${obj['num']:02X} {obj['name']:13s} pos {where}  state ${obj['state_ptr']:04X}  "
              f"colour ${obj['colour']:02X}  size ${obj['size']:02X} (x{obj['width']})  states {state_list}")
        if obj["name"] in ("surround", "game number", "author name", "null"):
            continue
        shown = set()
        for _, graphic_addr in obj["states"]:
            if graphic_addr in shown:
                continue
            shown.add(graphic_addr)
            print(f"   graphic ${graphic_addr:04X}:")
            for line in ascii_graphic(obj["graphics"][graphic_addr]):
                print("     " + line)
