"""Check ram_map.py against the running game (no window): start game 1, compare the object list with the ROM
table, then walk the hero to the yellow key, pick it up, and carry it. Prints PASS/FAIL per check and saves
frames to the directory given as the first argument (default: shots/verify).

Usage: python verify_ram.py [outdir]
"""

import os
import sys
from typing import Iterable

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, when run as a script
from engine import emulator as h
from engine import ram_map as M

ROM = os.path.join(h.HERE, "roms", "adventure.a26")
results = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(h.HERE, "shots", "verify")
    os.makedirs(out, exist_ok=True)
    c = h.Core()
    c.load(ROM)
    memory = c.ram
    assert memory is not None   # load() made the live view of the RAM
    ram = lambda a: int(memory[a - 0x80])

    def run(n: int, keys: Iterable[int] = ()) -> None:
        c.joy = set(keys)
        for _ in range(n):
            c.run()

    def snap(name: str) -> None:
        assert c.frame is not None   # run() has drawn a frame by now
        Image.fromarray(c.frame).save(os.path.join(out, f"{name}.png"))

    run(60)
    check("boot shows the number room", ram(M.ROOM) == M.NUMBER_ROOM, f"room={ram(M.ROOM):02X}")
    run(10, [h.JOY_START])
    run(30)
    snap("1_start")
    check("level byte = 0 (game 1)", ram(M.LEVEL) == 0, f"{ram(M.LEVEL):02X}")
    check("game active flag = 0", ram(M.GAME_ACTIVE) == 0, f"{ram(M.GAME_ACTIVE):02X}")
    check("hero starts in gold castle room $11", ram(M.ROOM) == 0x11, f"{ram(M.ROOM):02X}")
    check("nothing carried", M.carried_name(memory) is None, f"$9D={ram(M.CARRIED):02X}")

    # the object list must equal the ROM table Game1Objects ($F460, 49 bytes) - except things that already moved
    rom = open(ROM, "rb").read()
    table = rom[0x460:0x460 + 49]
    live = bytes(memory[0xA1 - 0x80:0xA1 - 0x80 + 49])
    diffs = [f"${0xA1 + i:02X}:{table[i]:02X}->{live[i]:02X}" for i in range(49) if table[i] != live[i]]
    check("object list $A1-$D1 = ROM Game1Objects (dragons/bat may have moved)", len(diffs) < 12,
          " ".join(diffs) or "identical")
    for name, addr in M.ITEMS.items():
        print(f"      {name:12s} room,x,y = {M.pos(memory, addr)}")
    for name, addr in M.DRAGONS.items():
        print(f"      {name:12s} room,x,y = {M.pos(memory, addr)}  state={ram(addr + M.DRAGON_STATE_OFFSET):02X}")

    # hero movement: x/y respond to the stick in the expected direction
    x0, y0 = ram(M.HERO_X), ram(M.HERO_Y)
    run(20, [h.JOY_LEFT])
    check("LEFT decreases $8B", ram(M.HERO_X) < x0, f"{x0:02X}->{ram(M.HERO_X):02X}")
    run(20, [h.JOY_UP])
    check("UP increases $8C", ram(M.HERO_Y) > y0, f"{y0:02X}->{ram(M.HERO_Y):02X}")

    # walk to the yellow key (same room, $20,$40 in game 1): steer until touching it
    _, kx, ky = M.pos(memory, M.YELLOW_KEY)
    for frame in range(600):
        if M.carried_name(memory):
            break
        keys = []
        if ram(M.HERO_X) > kx + 4:
            keys.append(h.JOY_LEFT)
        elif ram(M.HERO_X) < kx:
            keys.append(h.JOY_RIGHT)
        if ram(M.HERO_Y) < ky - 4:
            keys.append(h.JOY_UP)
        elif ram(M.HERO_Y) > ky + 4:
            keys.append(h.JOY_DOWN)
        run(1, keys)
    snap("2_key")
    check("touching the key picks it up", M.carried_name(memory) == "yellow key",
          f"$9D={ram(M.CARRIED):02X} ({M.carried_name(memory)}) after {frame} frames")

    # carried items follow the hero
    k0, h0 = M.pos(memory, M.YELLOW_KEY), ram(M.HERO_X)
    run(30, [h.JOY_RIGHT])
    k1, h1 = M.pos(memory, M.YELLOW_KEY), ram(M.HERO_X)
    snap("3_carry")
    dx, dy = ram(M.CARRY_DX), ram(M.CARRY_DY)
    off = ((k1[1] - h1) & 0xFF, (k1[2] - ram(M.HERO_Y)) & 0xFF)
    check("carried key = hero + offset ($9E,$9F)", h1 != h0 and min((off[0] - dx) & 0xFF, (dx - off[0]) & 0xFF) <= 3 and off[1] == dy,
          f"hero x {h0:02X}->{h1:02X}, key x {k0[1]:02X}->{k1[1]:02X}, offset now {off[0]:02X},{off[1]:02X}"
          f" stored {dx:02X},{dy:02X}")

    # fire drops it
    run(5, [h.JOY_B])
    run(5)
    check("FIRE drops it", M.carried_name(memory) is None, f"$9D={ram(M.CARRIED):02X}")

    print(f"\n{sum(results)}/{len(results)} checks passed; frames in {out}")


if __name__ == "__main__":
    main()
