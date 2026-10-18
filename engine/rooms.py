"""Decode Adventure's rooms straight out of the ROM: wall grids, colours, thin walls and exits.

Room table at $FE1B (Robinett's "room list"), 9 bytes per room:
  0-1 pointer to the wall graphics, 2 colour, 3 B&W colour,
  4 playfield control: bit 0 = right half MIRRORS the left (else it repeats), bit 2 = walls drawn in front
    of objects, bit 6 = right thin wall, bit 7 = left thin wall (the thin walls are the two TIA missiles),
  5-8 exits: up, RIGHT, down, LEFT (the disassembly comment says left/right the other way round - walking
    the game proved otherwise, see verify_exits.py). An exit >= $80 means "depends on the game number": the
    low bits index RoomDiffs ($FF32, 3 bytes per entry = game 1, 2, 3).
Wall graphics: 7 rows x 3 bytes (PF0, PF1, PF2) = the left 20 columns of a 40-column row.
TIA bit order: PF0 uses bits 4..7 (left to right), PF1 bits 7..0, PF2 bits 0..7.

Usage: python rooms.py  -> prints every room as ASCII and writes rooms.json
"""

import json
import os

from engine import paths

HERE = paths.ROOT
ROM_PATH = paths.ROM
ROOM_TABLE, ROOM_DIFFS = 0xFE1B, 0xFF32
N_ROOMS = 0x1F
ROWS, COLS = 7, 40
# Screen geometry, measured in the core's 160x228 frame (verify_rooms.py): column c = pixels 4c..4c+3;
# wall rows span these scan lines (the first and last rows are half height); walls cover lines 13-205.
ROW_LINES = [(13, 29), (30, 61), (62, 93), (94, 125), (126, 157), (158, 189), (190, 205)]
# Thin walls (TIA missiles), full height. On the 2600 their colour comes from whichever object is in the
# room (a hardware accident) - we draw them as walls in the room's own style.
THIN_WALL_LEFT_X, THIN_WALL_RIGHT_X = (11, 12), (148, 149)

NAMES = {0x00: "number room", 0x01: "light green room", 0x02: "below gold castle",
         0x03: "left of name", 0x04: "blue maze top", 0x05: "blue maze 1", 0x06: "blue maze bottom",
         0x07: "blue maze center", 0x08: "blue maze entry", 0x09: "catacombs middle",
         0x0A: "catacombs entry", 0x0B: "catacombs side", 0x0C: "side corridor", 0x0D: "side corridor 2",
         0x0E: "top entry room", 0x0F: "white castle", 0x10: "black castle", 0x11: "gold castle",
         0x12: "gold castle inside", 0x13: "black maze 1", 0x14: "black maze 2", 0x15: "black maze 3",
         0x16: "black maze entry", 0x17: "red maze 1", 0x18: "red maze top", 0x19: "red maze bottom",
         0x1A: "white castle inside", 0x1B: "black castle inside", 0x1C: "purple room",
         0x1D: "top entry room 2", 0x1E: "name room"}


# Exits the room table does NOT describe - hard-coded in the game's movement code (MoveGroundObject):
CASTLES = {  # castle room -> (interior room, portcullis RAM byte). Gate byte $1C = closed.
    0x11: (0x12, 0xC8), 0x0F: (0x1A, 0xC9), 0x10: (0x1B, 0xCA)}
SPECIAL_EXITS = [
    "castle gate open: walking up through it enters the interior ($11->$12, $0F->$1A, $10->$1B); walking "
    "down out of the interior returns to the castle room (x=$50, y=$2C). Gate closed: the normal exit table "
    "applies.",
    "room $03, walking off the RIGHT edge: goes to the secret name room $1E (x=$03) unless the dot ($A1) is "
    "still in room $15 - Robinett's Easter egg.",
    "the chalice in room $12 (gold castle interior) wins the game.",
]


def load_rom(path=None):
    return open(path or ROM_PATH, "rb").read()  # ROM_PATH: play.py points it at the ROM it found


def rd(rom, addr):
    """The ROM byte at a 2600 address (the 4 KB cartridge is mapped at $F000)."""
    return rom[addr & 0x0FFF]


def bits_left_half(pf0, pf1, pf2):
    """The three playfield bytes -> the 20 wall columns of a row's left half, left to right (each byte's
    bits run in its own order: TIA bit order in the docstring above)."""
    pf0_bits = [(pf0 >> bit) & 1 for bit in range(4, 8)]
    pf1_bits = [(pf1 >> bit) & 1 for bit in range(7, -1, -1)]
    pf2_bits = [(pf2 >> bit) & 1 for bit in range(0, 8)]
    return pf0_bits + pf1_bits + pf2_bits


def resolve_exit(rom, value, game):
    """Exit byte -> room number for game 1/2/3."""
    if value < 0x80:
        return value
    return rd(rom, ROOM_DIFFS + (value - 0x80) + (game - 1))


def decode_room(rom, room_number):
    entry = ROOM_TABLE + 9 * room_number  # 9 bytes a room
    gfx = rd(rom, entry) | rd(rom, entry + 1) << 8
    ctrl = rd(rom, entry + 4)
    grid = []
    for row in range(ROWS):
        left = bits_left_half(*(rd(rom, gfx + 3 * row + i) for i in range(3)))
        right = left[::-1] if ctrl & 1 else left  # mirrored, or the same again
        grid.append(left + right)
    raw_exits = [rd(rom, entry + 5 + i) for i in range(4)]
    exits = {}
    for game in (1, 2, 3):
        rooms = [resolve_exit(rom, value, game) for value in raw_exits]
        exits[game] = dict(zip(("up", "right", "down", "left"), rooms))
    return {"room": room_number, "name": NAMES.get(room_number, f"room {room_number:02X}"), "gfx": gfx,
            "colour": rd(rom, entry + 2), "bw_colour": rd(rom, entry + 3), "ctrl": ctrl,
            "mirrored": bool(ctrl & 1), "walls_in_front": bool(ctrl & 4),
            "thin_wall_left": bool(ctrl & 0x80), "thin_wall_right": bool(ctrl & 0x40), "grid": grid,
            "exits_raw": raw_exits, "exits": exits}


def decode_all(rom=None):
    rom = rom or load_rom()
    return [decode_room(rom, room_number) for room_number in range(N_ROOMS)]


def ascii_room(room):
    lines = [f"${room['room']:02X} {room['name']}  colour ${room['colour']:02X}  ctrl ${room['ctrl']:02X}"
             f"{' mirrored' if room['mirrored'] else ' repeated'}"
             f"{' +thinL' if room['thin_wall_left'] else ''}{' +thinR' if room['thin_wall_right'] else ''}"]
    lines += ["  " + "".join("#" if is_wall else "." for is_wall in row) for row in room["grid"]]
    exits = room["exits"]

    def listed(game):
        return " ".join(f"{side}={room_number:02X}" for side, room_number in exits[game].items())
    line = "  exits game1 " + listed(1)
    if exits[1] != exits[2]:
        line += "  | game2/3 " + listed(2)
    lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    rooms = decode_all()
    for room in rooms:
        print(ascii_room(room) + "\n")
    with open(os.path.join(HERE, "rooms.json"), "w") as f:
        json.dump(rooms, f, indent=1)
