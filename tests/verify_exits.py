"""Walk out of every opening of every room (game 1) and check the game takes us where rooms.py says.
The hero is placed beside each edge opening (write $8A/$8B/$8C), the stick held toward it, and the new room
read back from $8A.

Screen mapping used (measured in verify_rooms.py): column c covers frame pixels 4c..4c+3 and the hero's x is
in the same units; the hero's y is drawn at scan line ~ 13 + 2 * (104 - y).

Usage: python verify_exits.py
"""

import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, when run as a script
from engine import emulator as h
from engine import ram_map as M
from engine import rooms as R
from shared.types import Point

STICK = {"up": h.JOY_UP, "down": h.JOY_DOWN, "left": h.JOY_LEFT, "right": h.JOY_RIGHT}


def y_for_line(line: int) -> int:
    return 104 - (line - 13) // 2


def openings(room: dict[str, Any]) -> dict[str, Point]:
    g = room["grid"]
    mid_rows = range(1, R.ROWS - 1)
    found: dict[str, Point] = {}
    for col in range(14, 26):          # top/bottom gaps are in the middle in this game
        if not g[0][col] and "up" not in found:
            found["up"] = (col * 4 + 2, y_for_line(20))
        if not g[R.ROWS - 1][col] and "down" not in found:
            found["down"] = (col * 4 + 2, y_for_line(196))
    for r in mid_rows:
        line = sum(R.ROW_LINES[r]) // 2
        if not g[r][0] and not g[r][1] and "left" not in found:
            found["left"] = (6, y_for_line(line))
        if not g[r][R.COLS - 1] and not g[r][R.COLS - 2] and "right" not in found:
            found["right"] = (R.COLS * 4 - 8, y_for_line(line))
    return found


def main() -> None:
    c = h.Core()
    c.load(os.path.join(h.HERE, "roms", "adventure.a26"))
    ram = c.ram
    assert ram is not None   # load() made the live view of the RAM
    run = lambda n: [c.run() for _ in range(n)]
    c.joy = set(); run(60)
    c.joy = {h.JOY_START}; run(10)
    c.joy = set(); run(30)
    ok = bad = 0
    for room in R.decode_all()[1:]:
        for direction, (x, y) in openings(room).items():
            for _ in range(3):
                for addr, v in ((M.ROOM, room["room"]), (M.PREV_ROOM, room["room"]), (M.HERO_X, x), (M.PREV_X, x),
                                (M.HERO_Y, y), (M.PREV_Y, y)):
                    ram[addr - 0x80] = v
                c.joy = set(); c.run()
            c.joy = {STICK[direction]}
            got: int | None = None
            for _ in range(90):
                prev = (int(ram[M.HERO_X - 0x80]), int(ram[M.HERO_Y - 0x80]))
                c.run()
                cur = (int(ram[M.HERO_X - 0x80]), int(ram[M.HERO_Y - 0x80]))
                # a room change, or a jump across the screen (an exit that leads back into the same room)
                if ram[M.ROOM - 0x80] != room["room"] or abs(cur[0] - prev[0]) > 40 or abs(cur[1] - prev[1]) > 40:
                    got = int(ram[M.ROOM - 0x80])
                    break
            want = room["exits"][1][direction]
            if got == want:
                ok += 1
            else:
                bad += 1
                print(f"${room['room']:02X} {room['name']:22s} {direction:5s} expected ${want:02X} got "
                      + (f"${got:02X}" if got is not None else "no room change (blocked?)"))
    print(f"\n{ok}/{ok + bad} exits match rooms.py (game 1)")


if __name__ == "__main__":
    main()
