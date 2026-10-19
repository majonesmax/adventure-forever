"""Check ram_map.py against the running game (no window): start game 1, compare the object list with the ROM
table, then walk the hero to the yellow key, pick it up, and carry it. Prints PASS/FAIL per check and saves
frames to the directory given as the first argument (default: shots/verify).

Usage: python verify_ram.py [outdir]
"""

import os
import sys
from typing import Iterable

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, as a script
from engine import emulator as h
from engine import ram_map as M
from shared.types import RamView

ROM = os.path.join(h.HERE, "roms", "adventure.a26")
results = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


class Session:
    """The running game, and the folder its frames are saved to."""

    def __init__(self, out: str):
        self.out = out
        self.core = h.Core()
        self.core.load(ROM)
        memory = self.core.ram
        assert memory is not None   # load() made the live view of the RAM
        self.memory: RamView = memory

    def byte(self, address: int) -> int:
        return int(self.memory[address - 0x80])

    def run(self, frames: int, keys: Iterable[int] = ()) -> None:
        self.core.joy = set(keys)
        for _ in range(frames):
            self.core.run()

    def snap(self, name: str) -> None:
        assert self.core.frame is not None   # run() has drawn a frame by now
        Image.fromarray(self.core.frame).save(os.path.join(self.out, f"{name}.png"))


def check_start(game: Session) -> None:
    game.run(60)
    check("boot shows the number room", game.byte(M.ROOM) == M.NUMBER_ROOM, f"room={game.byte(M.ROOM):02X}")
    game.run(10, [h.JOY_START])
    game.run(30)
    game.snap("1_start")
    check("level byte = 0 (game 1)", game.byte(M.LEVEL) == 0, f"{game.byte(M.LEVEL):02X}")
    check("game active flag = 0", game.byte(M.GAME_ACTIVE) == 0, f"{game.byte(M.GAME_ACTIVE):02X}")
    check("hero starts in gold castle room $11", game.byte(M.ROOM) == 0x11, f"{game.byte(M.ROOM):02X}")
    check("nothing carried", M.carried_name(game.memory) is None, f"$9D={game.byte(M.CARRIED):02X}")


def check_object_list(game: Session) -> None:
    """The object list must equal the ROM table Game1Objects ($F460, 49 bytes) - except things that already
    moved."""
    rom = open(ROM, "rb").read()
    table = rom[0x460:0x460 + 49]
    live = bytes(game.memory[0xA1 - 0x80:0xA1 - 0x80 + 49])
    diffs = [f"${0xA1 + i:02X}:{table[i]:02X}->{live[i]:02X}" for i in range(49) if table[i] != live[i]]
    check("object list $A1-$D1 = ROM Game1Objects (dragons/bat may have moved)", len(diffs) < 12,
          " ".join(diffs) or "identical")
    for name, addr in M.ITEMS.items():
        print(f"      {name:12s} room,x,y = {M.pos(game.memory, addr)}")
    for name, addr in M.DRAGONS.items():
        dragon_state = game.byte(addr + M.DRAGON_STATE_OFFSET)
        print(f"      {name:12s} room,x,y = {M.pos(game.memory, addr)}  state={dragon_state:02X}")


def check_movement(game: Session) -> None:
    """x/y respond to the stick in the expected direction."""
    start_x, start_y = game.byte(M.HERO_X), game.byte(M.HERO_Y)
    game.run(20, [h.JOY_LEFT])
    check("LEFT decreases $8B", game.byte(M.HERO_X) < start_x, f"{start_x:02X}->{game.byte(M.HERO_X):02X}")
    game.run(20, [h.JOY_UP])
    check("UP increases $8C", game.byte(M.HERO_Y) > start_y, f"{start_y:02X}->{game.byte(M.HERO_Y):02X}")


def walk_to_key(game: Session) -> int:
    """Walk to the yellow key (same room, $20,$40 in game 1), steering until touching it: the frames it
    took."""
    _, key_x, key_y = M.pos(game.memory, M.YELLOW_KEY)
    frame = 0
    for frame in range(600):
        if M.carried_name(game.memory):
            break
        game.run(1, steer(game, key_x, key_y))
    return frame


def steer(game: Session, key_x: int, key_y: int) -> list[int]:
    keys = []
    if game.byte(M.HERO_X) > key_x + 4:
        keys.append(h.JOY_LEFT)
    elif game.byte(M.HERO_X) < key_x:
        keys.append(h.JOY_RIGHT)
    if game.byte(M.HERO_Y) < key_y - 4:
        keys.append(h.JOY_UP)
    elif game.byte(M.HERO_Y) > key_y + 4:
        keys.append(h.JOY_DOWN)
    return keys


def check_carry(game: Session) -> None:
    """Carried items follow the hero, at the offset the game stores ($9E, $9F)."""
    key_before, hero_before = M.pos(game.memory, M.YELLOW_KEY), game.byte(M.HERO_X)
    game.run(30, [h.JOY_RIGHT])
    key_after, hero_after = M.pos(game.memory, M.YELLOW_KEY), game.byte(M.HERO_X)
    game.snap("3_carry")
    dx, dy = game.byte(M.CARRY_DX), game.byte(M.CARRY_DY)
    off = ((key_after[1] - hero_after) & 0xFF, (key_after[2] - game.byte(M.HERO_Y)) & 0xFF)
    near_x = min((off[0] - dx) & 0xFF, (dx - off[0]) & 0xFF) <= 3
    check("carried key = hero + offset ($9E,$9F)", hero_after != hero_before and near_x and off[1] == dy,
          f"hero x {hero_before:02X}->{hero_after:02X}, key x {key_before[1]:02X}->{key_after[1]:02X}, "
          f"offset now {off[0]:02X},{off[1]:02X} stored {dx:02X},{dy:02X}")


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(h.HERE, "shots", "verify")
    os.makedirs(out, exist_ok=True)
    game = Session(out)
    check_start(game)
    check_object_list(game)
    check_movement(game)
    frames = walk_to_key(game)
    game.snap("2_key")
    check("touching the key picks it up", M.carried_name(game.memory) == "yellow key",
          f"$9D={game.byte(M.CARRIED):02X} ({M.carried_name(game.memory)}) after {frames} frames")
    check_carry(game)
    game.run(5, [h.JOY_B])   # fire drops it
    game.run(5)
    check("FIRE drops it", M.carried_name(game.memory) is None, f"$9D={game.byte(M.CARRIED):02X}")
    print(f"\n{sum(results)}/{len(results)} checks passed; frames in {out}")


if __name__ == "__main__":
    main()
