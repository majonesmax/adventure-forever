"""Decode Adventure's rooms straight out of the ROM: wall grids, colours, thin walls and exits.

Room table at $FE1B (Robinett's "room list"), 9 bytes per room:
  0-1 pointer to the wall graphics, 2 colour, 3 B&W colour,
  4 playfield control: bit 0 = right half MIRRORS the left (else it repeats), bit 2 = walls drawn in front
    of objects, bit 6 = right thin wall, bit 7 = left thin wall (the thin walls are the two TIA missiles),
  5-8 exits: up, RIGHT, down, LEFT (the disassembly comment says left/right the other way round - walking
    the game proved otherwise, see verify_exits.py). An exit >= $80 means "depends on the game number": the low bits index
    RoomDiffs ($FF32, 3 bytes per entry = game 1, 2, 3).
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
# Thin walls (TIA missiles), full height. On the 2600 their colour comes from whichever object is in the room
# (a hardware accident) - we draw them as walls in the room's own style.
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
    "castle gate open: walking up through it enters the interior ($11->$12, $0F->$1A, $10->$1B); walking down "
    "out of the interior returns to the castle room (x=$50, y=$2C). Gate closed: the normal exit table applies.",
    "room $03, walking off the RIGHT edge: goes to the secret name room $1E (x=$03) unless the dot ($A1) is "
    "still in room $15 - Robinett's Easter egg.",
    "the chalice in room $12 (gold castle interior) wins the game.",
]


def load_rom(path=None):
    return open(path or ROM_PATH, "rb").read()  # ROM_PATH: play.py points it at the ROM it found


def rd(rom, addr):
    return rom[addr & 0x0FFF]  # 4 KB cartridge mapped at $F000


def bits_left_half(pf0, pf1, pf2):
    return ([(pf0 >> b) & 1 for b in range(4, 8)] + [(pf1 >> b) & 1 for b in range(7, -1, -1)]
            + [(pf2 >> b) & 1 for b in range(0, 8)])


def resolve_exit(rom, value, game):
    """Exit byte -> room number for game 1/2/3."""
    if value < 0x80:
        return value
    return rd(rom, ROOM_DIFFS + (value - 0x80) + (game - 1))


def decode_room(rom, n):
    e = ROOM_TABLE + 9 * n
    gfx = rd(rom, e) | rd(rom, e + 1) << 8
    ctrl = rd(rom, e + 4)
    grid = []
    for r in range(ROWS):
        left = bits_left_half(*(rd(rom, gfx + 3 * r + i) for i in range(3)))
        grid.append(left + (left[::-1] if ctrl & 1 else left))
    raw_exits = [rd(rom, e + 5 + i) for i in range(4)]
    return {"room": n, "name": NAMES.get(n, f"room {n:02X}"), "gfx": gfx, "colour": rd(rom, e + 2),
            "bw_colour": rd(rom, e + 3), "ctrl": ctrl, "mirrored": bool(ctrl & 1),
            "walls_in_front": bool(ctrl & 4), "thin_wall_left": bool(ctrl & 0x80),
            "thin_wall_right": bool(ctrl & 0x40), "grid": grid,
            "exits_raw": raw_exits,
            "exits": {g: dict(zip(("up", "right", "down", "left"), (resolve_exit(rom, v, g) for v in raw_exits)))
                      for g in (1, 2, 3)}}


def decode_all(rom=None):
    rom = rom or load_rom()
    return [decode_room(rom, n) for n in range(N_ROOMS)]


def ascii_room(room):
    lines = [f"${room['room']:02X} {room['name']}  colour ${room['colour']:02X}  ctrl ${room['ctrl']:02X}"
             f"{' mirrored' if room['mirrored'] else ' repeated'}"
             f"{' +thinL' if room['thin_wall_left'] else ''}{' +thinR' if room['thin_wall_right'] else ''}"]
    lines += ["  " + "".join("#" if b else "." for b in row) for row in room["grid"]]
    ex = room["exits"]
    lines.append("  exits game1 " + " ".join(f"{k}={v:02X}" for k, v in ex[1].items())
                 + ("" if ex[1] == ex[2] else "  | game2/3 " + " ".join(f"{k}={v:02X}" for k, v in ex[2].items())))
    return "\n".join(lines)


if __name__ == "__main__":
    rooms = decode_all()
    for r in rooms:
        print(ascii_room(r) + "\n")
    with open(os.path.join(HERE, "rooms.json"), "w") as f:
        json.dump(rooms, f, indent=1)
