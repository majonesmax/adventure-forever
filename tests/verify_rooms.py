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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, when run as a script
from engine import emulator as h
from engine import ram_map as M
from engine import rooms as R

args = [a for a in sys.argv[1:] if a != "--reveal"]
reveal = "--reveal" in sys.argv
out = args[0] if args else os.path.join(h.HERE, "shots", "rooms")
os.makedirs(out, exist_ok=True)
rom_path = os.path.join(h.HERE, "roms", "adventure.a26")
DARK = [n for n in range(1, R.N_ROOMS) if R.decode_room(R.load_rom(), n)["colour"] == 0x08]
if reveal:
    rom = bytearray(R.load_rom())
    for n in DARK:
        rom[(R.ROOM_TABLE + 9 * n + 2) & 0x0FFF] = 0x00  # colour byte -> black
    rom_path = os.path.join(out, "adventure_revealed.a26")
    open(rom_path, "wb").write(rom)
c = h.Core()
c.load(rom_path)
GATE_CELLS = {(4, 19), (4, 20)}  # the portcullis sits here in the three castle rooms
CASTLES = (0x0F, 0x10, 0x11)
c.joy = set()
for _ in range(60):
    c.run()
c.joy = {h.JOY_START}
for _ in range(10):
    c.run()
c.joy = set()
for _ in range(30):
    c.run()

rooms = R.decode_all()
frames = {}
for room in rooms[1:]:
    for _ in range(6):  # hold the hero in this room, mid-screen, for a few frames
        c.ram[M.ROOM - 0x80], c.ram[M.PREV_ROOM - 0x80] = room["room"], room["room"]
        c.run()
    frames[room["room"]] = f = c.frame.copy()
    Image.fromarray(f).save(os.path.join(out, f"room_{room['room']:02X}.png"))

bg = np.array([162, 162, 161])
wall_masks = {}
for n, f in frames.items():
    if rooms[n]["colour"] == 0x08 and not reveal:
        continue  # walls in the background grey: invisible except inside the hero's lit square
    is_bg = np.all(np.abs(f.astype(int) - bg) < 8, axis=2)
    m = ~is_bg
    m[:13], m[207:] = False, False  # the black border above/below the room (black castle walls ARE black)
    wall_masks[n] = m

# which wall row does each scan line belong to? pick the row whose bits match that line best in all rooms
line_row = {}
for y in range(0, 228):
    scores = []
    for r in range(R.ROWS):
        s = 0
        for n, m in wall_masks.items():
            want = np.repeat(np.array(rooms[n]["grid"][r], bool), 4)
            s += int((m[y] == want).sum())
        scores.append(s)
    best = int(np.argmax(scores))
    if scores[best] >= 0.93 * 160 * len(wall_masks):
        line_row[y] = best
spans = {}
for y, r in line_row.items():
    spans.setdefault(r, []).append(y)
for r in range(R.ROWS):
    ys = spans.get(r, [])
    print(f"row {r}: lines {min(ys)}-{max(ys)} ({len(ys)} lines)" if ys else f"row {r}: NOT FOUND")

# per-room cell comparison using the measured row spans (sample the middle line of each span, centre of cell)
bad = 0
for n, m in wall_masks.items():
    errs, covered = [], 0
    f = frames[n].astype(int)
    px = f[m].reshape(-1, 3)
    vals, counts = np.unique(px, axis=0, return_counts=True)
    wall_rgb = vals[np.argmax(counts)]  # the commonest non-background colour = the wall colour
    for r in range(R.ROWS):
        ys = spans.get(r)
        if not ys:
            continue
        y = ys[len(ys) // 2]
        for col in range(R.COLS):
            p = f[y, col * 4 + 2]
            if n in CASTLES and (r, col) in GATE_CELLS:
                continue
            if np.abs(p - wall_rgb).max() >= 8 and np.abs(p - bg).max() >= 8:
                covered += 1  # an object is drawn over this cell - can't judge the wall here
                continue
            if bool(m[y, col * 4 + 2]) != bool(rooms[n]["grid"][r][col]):
                errs.append((r, col, tuple(int(v) for v in p)))
    bad += bool(errs)
    note = f"  ({covered} cells hidden by objects)" if covered else ""
    print(f"${n:02X} {rooms[n]['name']:22s} {'OK' if not errs else f'{len(errs)} cells differ: {errs[:4]}'}{note}")
skipped = sorted(set(frames) - set(wall_masks))
print(f"\n{len(wall_masks) - bad}/{len(wall_masks)} visible rooms match; invisible-wall rooms skipped: "
      + " ".join(f"${n:02X}" for n in skipped))
