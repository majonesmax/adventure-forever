"""The 2600's 128 NTSC colours as THIS emulator core draws them, measured rather than copied from a table:
a patched copy of the ROM (in the scratch dir given, never the real ROM) swaps the background colour the game
loads at $F13C (`lda #$08`) for each colour in turn; we run a few frames and sample the floor.
Each colour is probed in its own process: the Stella core keeps global state and does not survive being
unloaded and re-loaded many times in one process (that gave random black entries).

Usage: python palette.py <scratch dir>   -> writes palette_ntsc.json (colour byte -> [r, g, b])
"""

import json
import os
import subprocess
import sys

import numpy as np

from engine import emulator as h
from engine import rooms as R

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "palette_ntsc.json")


def load():
    with open(OUT) as f:
        return {int(k): tuple(v) for k, v in json.load(f).items()}


def probe(path):
    """Child process: load one patched ROM, print the floor colour."""
    c = h.Core()
    c.load(path)
    for _ in range(60):
        c.run()
    f = c.frame.astype(int)
    # number room: plain floor in the lower left (clear of the game-number digit in the middle)
    print(json.dumps([int(v) for v in np.median(f[150:170, 20:50].reshape(-1, 3), axis=0)]))


def main():
    if sys.argv[1] == "--probe":
        return probe(sys.argv[2])
    scratch = sys.argv[1]
    os.makedirs(scratch, exist_ok=True)
    rom = bytearray(R.load_rom())
    assert rom[0x13C] == 0xA9 and rom[0x13D] == 0x08, "unexpected code at $F13C"
    pal = {}
    for colour in range(0, 256, 2):  # bit 0 is ignored by the TIA
        rom[0x13D] = colour
        path = os.path.join(scratch, f"palette_probe_{colour:02X}.a26")
        open(path, "wb").write(rom)
        out = subprocess.run([sys.executable, __file__, "--probe", path], capture_output=True, text=True).stdout
        pal[colour] = json.loads(out.strip().splitlines()[-1])
    with open(OUT, "w") as f:
        json.dump(pal, f, indent=0)
    print(f"{len(pal)} colours -> {OUT}; $08 = {pal[0x08]}, $1A = {pal[0x1A]}, $86 = {pal[0x86]}")


if __name__ == "__main__":
    main()
