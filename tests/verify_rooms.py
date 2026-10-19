"""Check rooms.py against the emulator: put the hero in each room (write $8A), let the game draw it, and
compare every wall cell with the real frame. Also measures which scan lines each of the 7 wall rows covers.
Rooms whose walls are the background colour (the dark catacombs / black maze) can't be seen and are skipped.

With --reveal, a patched COPY of the ROM (written to outdir) gives those dark rooms black walls so they can
be checked too. The real ROM is never touched.

Usage: python verify_rooms.py [--reveal] [outdir]   (default shots/rooms)
"""

import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, as a script
from engine import emulator as h
from engine import ram_map as M
from engine import rooms as R
from shared.types import Mask, Picture

GATE_CELLS = {(4, 19), (4, 20)}  # the portcullis sits here in the three castle rooms
CASTLES = (0x0F, 0x10, 0x11)
BACKGROUND = np.array([162, 162, 161])   # the 2600's floor grey
DARK_COLOUR = 0x08                       # walls in the background grey: the dark rooms
Errors = list[tuple[int, int, tuple[int, ...]]]   # (row, column, the frame's colour there)


def rom_to_use(out: str, reveal: bool) -> str:
    """The real ROM - or, with --reveal, a patched copy in `out` where the dark rooms have black walls."""
    rom_path = os.path.join(h.HERE, "roms", "adventure.a26")
    if not reveal:
        return rom_path
    dark = [number for number in range(1, R.N_ROOMS)
            if R.decode_room(R.load_rom(), number)["colour"] == DARK_COLOUR]
    rom = bytearray(R.load_rom())
    for number in dark:
        rom[(R.ROOM_TABLE + 9 * number + 2) & 0x0FFF] = 0x00  # colour byte -> black
    revealed = os.path.join(out, "adventure_revealed.a26")
    open(revealed, "wb").write(rom)
    return revealed


def frames_of_every_room(rom_path: str, out: str, rooms: list[R.Room]) -> dict[int, Picture]:
    """Start game 1, then hold the hero in each room for a few frames and keep the frame the game draws."""
    core = h.Core()
    core.load(rom_path)
    memory = core.ram
    assert memory is not None   # load() made the live view of the RAM
    for held, frame_count in ((set(), 60), ({h.JOY_START}, 10), (set(), 30)):
        core.joy = held
        for _ in range(frame_count):
            core.run()
    frames: dict[int, Picture] = {}
    for room in rooms[1:]:
        for _ in range(6):  # hold the hero in this room, mid-screen, for a few frames
            memory[M.ROOM - 0x80], memory[M.PREV_ROOM - 0x80] = room["room"], room["room"]
            core.run()
        assert core.frame is not None   # the game has drawn the room
        frames[room["room"]] = frame = core.frame.copy()
        Image.fromarray(frame).save(os.path.join(out, f"room_{room['room']:02X}.png"))
    return frames


def wall_masks_of(frames: dict[int, Picture], rooms: list[R.Room], reveal: bool) -> dict[int, Mask]:
    masks: dict[int, Mask] = {}
    for number, frame in frames.items():
        if rooms[number]["colour"] == DARK_COLOUR and not reveal:
            continue  # walls in the background grey: invisible except inside the hero's lit square
        is_background = np.all(np.abs(frame.astype(int) - BACKGROUND) < 8, axis=2)
        mask = ~is_background
        mask[:13], mask[207:] = False, False  # the black border above/below (black castle walls ARE black)
        masks[number] = mask
    return masks


def row_spans(masks: dict[int, Mask], rooms: list[R.Room]) -> dict[int, list[int]]:
    """Which wall row each scan line belongs to - the row whose bits match that line best in all rooms -
    as row -> its lines."""
    line_row: dict[int, int] = {}
    for y in range(0, 228):
        scores = []
        for row in range(R.ROWS):
            score = 0
            for number, mask in masks.items():
                want = np.repeat(np.array(rooms[number]["grid"][row], bool), 4)
                score += int((mask[y] == want).sum())
            scores.append(score)
        best = int(np.argmax(scores))
        if scores[best] >= 0.93 * 160 * len(masks):
            line_row[y] = best
    spans: dict[int, list[int]] = {}
    for y, row in line_row.items():
        spans.setdefault(row, []).append(y)
    return spans


def compare_room(number: int, frame_picture: Picture, mask: Mask, room: R.Room,
                 spans: dict[int, list[int]]) -> tuple[Errors, int]:
    """Every wall cell against the frame, sampling the middle line of each row and the centre of each cell:
    (the cells that differ, how many were hidden by objects)."""
    errors: Errors = []
    covered = 0
    frame = frame_picture.astype(int)
    colours, counts = np.unique(frame[mask].reshape(-1, 3), axis=0, return_counts=True)
    wall_rgb = colours[np.argmax(counts)]  # the commonest non-background colour = the wall colour
    for row in range(R.ROWS):
        lines = spans.get(row)
        if not lines:
            continue
        y = lines[len(lines) // 2]
        for col in range(R.COLS):
            pixel = frame[y, col * 4 + 2]
            if number in CASTLES and (row, col) in GATE_CELLS:
                continue
            if np.abs(pixel - wall_rgb).max() >= 8 and np.abs(pixel - BACKGROUND).max() >= 8:
                covered += 1  # an object is drawn over this cell - can't judge the wall here
                continue
            if bool(mask[y, col * 4 + 2]) != bool(room["grid"][row][col]):
                errors.append((row, col, tuple(int(value) for value in pixel)))
    return errors, covered


def main() -> None:
    args = [arg for arg in sys.argv[1:] if arg != "--reveal"]
    reveal = "--reveal" in sys.argv
    out = args[0] if args else os.path.join(h.HERE, "shots", "rooms")
    os.makedirs(out, exist_ok=True)
    rom_path = rom_to_use(out, reveal)
    rooms = R.decode_all()
    frames = frames_of_every_room(rom_path, out, rooms)
    masks = wall_masks_of(frames, rooms, reveal)
    spans = row_spans(masks, rooms)
    for row in range(R.ROWS):
        lines = spans.get(row, [])
        found = f"lines {min(lines)}-{max(lines)} ({len(lines)} lines)" if lines else "NOT FOUND"
        print(f"row {row}: {found}")
    bad = 0
    for number, mask in masks.items():
        errors, covered = compare_room(number, frames[number], mask, rooms[number], spans)
        bad += bool(errors)
        note = f"  ({covered} cells hidden by objects)" if covered else ""
        verdict = "OK" if not errors else f"{len(errors)} cells differ: {errors[:4]}"
        print(f"${number:02X} {rooms[number]['name']:22s} {verdict}{note}")
    skipped = sorted(set(frames) - set(masks))
    print(f"\n{len(masks) - bad}/{len(masks)} visible rooms match; invisible-wall rooms skipped: "
          + " ".join(f"${number:02X}" for number in skipped))


if __name__ == "__main__":
    main()
