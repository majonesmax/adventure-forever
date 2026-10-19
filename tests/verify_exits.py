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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, as a script
from engine import emulator as h
from engine import ram_map as M
from engine import rooms as R
from shared.types import Point, RamView

STICK = {"up": h.JOY_UP, "down": h.JOY_DOWN, "left": h.JOY_LEFT, "right": h.JOY_RIGHT}


def y_for_line(line: int) -> int:
    return 104 - (line - 13) // 2


def openings(room: dict[str, Any]) -> dict[str, Point]:
    grid = room["grid"]
    mid_rows = range(1, R.ROWS - 1)
    found: dict[str, Point] = {}
    for col in range(14, 26):          # top/bottom gaps are in the middle in this game
        if not grid[0][col] and "up" not in found:
            found["up"] = (col * 4 + 2, y_for_line(20))
        if not grid[R.ROWS - 1][col] and "down" not in found:
            found["down"] = (col * 4 + 2, y_for_line(196))
    for row in mid_rows:
        line = sum(R.ROW_LINES[row]) // 2
        if not grid[row][0] and not grid[row][1] and "left" not in found:
            found["left"] = (6, y_for_line(line))
        if not grid[row][R.COLS - 1] and not grid[row][R.COLS - 2] and "right" not in found:
            found["right"] = (R.COLS * 4 - 8, y_for_line(line))
    return found


def run(core: h.Core, frames: int, held: set[int]) -> None:
    core.joy = held
    for _ in range(frames):
        core.run()


def place_hero(core: h.Core, ram: RamView, room: dict[str, Any], hero: Point) -> None:
    """The hero in `room` at `hero` (and the game's bounce-back position with it), held there 3 frames."""
    x, y = hero
    writes = ((M.ROOM, room["room"]), (M.PREV_ROOM, room["room"]), (M.HERO_X, x), (M.PREV_X, x),
              (M.HERO_Y, y), (M.PREV_Y, y))
    for _ in range(3):
        for addr, value in writes:
            ram[addr - 0x80] = value
        run(core, 1, set())


def walk_out(core: h.Core, ram: RamView, room: dict[str, Any], direction: str) -> int | None:
    """Hold the stick toward `direction`: the room the hero ends up in, or None if he never leaves."""
    core.joy = {STICK[direction]}
    for _ in range(90):
        before = (int(ram[M.HERO_X - 0x80]), int(ram[M.HERO_Y - 0x80]))
        core.run()
        now = (int(ram[M.HERO_X - 0x80]), int(ram[M.HERO_Y - 0x80]))
        jumped = abs(now[0] - before[0]) > 40 or abs(now[1] - before[1]) > 40
        # a room change, or a jump across the screen (an exit that leads back into the same room)
        if ram[M.ROOM - 0x80] != room["room"] or jumped:
            return int(ram[M.ROOM - 0x80])
    return None


def main() -> None:
    core = h.Core()
    core.load(os.path.join(h.HERE, "roms", "adventure.a26"))
    ram = core.ram
    assert ram is not None   # load() made the live view of the RAM
    run(core, 60, set())
    run(core, 10, {h.JOY_START})
    run(core, 30, set())
    ok = bad = 0
    for room in R.decode_all()[1:]:
        for direction, hero in openings(room).items():
            place_hero(core, ram, room, hero)
            got = walk_out(core, ram, room, direction)
            want = room["exits"][1][direction]
            if got == want:
                ok += 1
                continue
            bad += 1
            arrived = f"${got:02X}" if got is not None else "no room change (blocked?)"
            print(f"${room['room']:02X} {room['name']:22s} {direction:5s} expected ${want:02X} got {arrived}")
    print(f"\n{ok}/{ok + bad} exits match rooms.py (game 1)")


if __name__ == "__main__":
    main()
