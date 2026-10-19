"""Golden-image test: every look, with every cast in every world, must keep drawing exactly the same pixels.

Builds a fixed set of game moments from the real emulator (boot, reset, then objects placed by writing RAM),
renders each in every look with every cast and world (keys like "nes", "snes+classic", "nes@pbj" - see
looks/base.py), and compares a SHA-256 of each screen with tests/golden_hashes.json. Only hashes are
stored: the tests keep no pictures of the game (whose walls and graphics come from the ROM) - the one gameplay
clip in the repository is the README's demo GIF.

Needs roms/adventure.a26 and the Stella core (cores/), so it runs locally, not in CI.
The references were made with the Stella core b52ccb02e - the one tools/get_core.py installs on every
platform - and pass unchanged on 2c3d702 too (try another core with ADVENTURE_CORE=<path to it>).

Usage: python tests/golden.py            compare; on a mismatch the screen is saved to
                                                   shots/golden_fail/ so you can look at it
       python tests/golden.py --update   accept the current pictures as the new reference
"""

import hashlib
import json
import os
import sys
from typing import Iterable, Sequence

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import content  # noqa: E402
import looks  # noqa: E402
from app import transitions as TR  # noqa: E402
from engine import emulator as h  # noqa: E402
from engine import ram_map as M  # noqa: E402
from engine.state import Game  # noqa: E402
from looks.base import RoomLook  # noqa: E402
from shared.types import Picture, Point, RamView  # noqa: E402

Scenario = tuple[list[RamView], list[int], list[int]]   # (RAM snapshots, frame numbers, indices to hash)

HASHES = os.path.join(ROOT, "tests", "golden_hashes.json")              # public casts and worlds only
PRIVATE_HASHES = os.path.join(ROOT, "private", "golden_hashes.json")   # with a private one (never published)
FAIL_DIR = os.path.join(ROOT, "shots", "golden_fail")


# ---- game moments -------------------------------------------------------------------------------------

def boot(game: int) -> tuple[h.Core, RamView, RamView]:
    """The emulator after power-on, GAME SELECT to `game`, RESET: (core, ram copy).

    The console switches are held for a fixed number of frames, but the waits after them count from the frame
    the game *sees* the switch released (its switch byte, ram_map.SWITCHES): cores differ in how many frames a
    switch takes to arrive (SELECT: Stella b52ccb02e at once, 2c3d702 two frames late), and counting this way
    puts every core at the same moment of the game.
    """
    core = h.Core()
    core.load(os.path.join(ROOT, "roms", "adventure.a26"))
    ram = core.ram
    assert ram is not None   # load() made the live view of the RAM

    def run(frames: int, keys: Iterable[int] = ()) -> None:
        core.joy.clear()
        core.joy.update(keys)
        for _ in range(frames):
            core.run()

    def press(key: int, bit: int, then: int, seen_after: int) -> None:
        """Hold `key` 8 frames, release it; once the game sees the release, wait out the rest of `then`
        frames - `seen_after` is how many frames the reference core (b52ccb02e) takes to show the release."""
        run(8, {key})
        for _ in range(12):  # until the game sees the switch released
            run(1)
            if ram[M.SWITCHES - 0x80] & bit:
                break
        run(then - seen_after)
    run(60)
    for _ in range(game - 1):
        press(h.JOY_SELECT, 0x02, 20, seen_after=1)
    title = ram.copy()
    press(h.JOY_START, 0x01, 60, seen_after=2)
    return core, title, ram.copy()


def poke(ram: RamView, values: dict[int, int]) -> RamView:
    out = ram.copy()
    for addr, value in values.items():
        out[addr - 0x80] = value
    return out


def place(room: int, hero: Point, objs: Sequence[tuple[int, ...]] = (),
          extra: dict[int, int] | None = None) -> dict[int, int]:
    """RAM edits: hero in `room` at `hero`, objects (addr, x, y[, state]) in the same room."""
    edits = {0x8A: room, 0x8B: hero[0], 0x8C: hero[1]}
    for addr, x, y, *state in objs:
        edits.update({addr: room, addr + 1: x, addr + 2: y})
        if state:
            edits[addr + 4] = state[0]
    edits.update(extra or {})
    return edits


def scenarios(game1: RamView, game2: RamView, title: RamView) -> dict[str, Scenario]:
    """name -> (list of RAM snapshots drawn in order, frame numbers to draw them at, indices to hash)."""
    moments: dict[str, Scenario] = {}
    moments["title"] = ([title, title], [0, 31], [0, 1])
    moments["start_game1"] = ([game1], [0], [0])
    # game 2 starts with the bat flying off with the sword; its path depends on when the game saw the last
    # input, which cores deliver a frame or two apart - so place the two where the reference core has them
    bat_and_sword = {0xCB: 0x11, 0xCC: 0x20, 0xCD: 0x1E, 0xCF: 0x00,     # the bat (room, x, y, state)
                     0xB6: 0x11, 0xB7: 0x28, 0xB8: 0x1E}                 # the sword
    moments["start_game2"] = ([poke(game2, bat_and_sword)], [0], [0])
    dragons = [(0xA4, 0x30, 0x40, 0), (0xA9, 0x60, 0x40, 3), (0xAE, 0x90, 0x40, 1)]
    moments["dragons"] = ([poke(game1, place(0x0F, (0x50, 0x20), dragons))], [0], [0])
    moments["eaten"] = ([poke(game1, place(0x11, (0x50, 0x20), [(0xA9, 0x50, 0x24, 2)]))], [0], [0])
    items = [(0xB6, 0x30, 0x30), (0xBF, 0x50, 0x50), (0xC2, 0x70, 0x50), (0xC5, 0x90, 0x50),
             (0xB3, 0x30, 0x55), (0xB9, 0x90, 0x30), (0xCB, 0x60, 0x30, 2)]
    moments["items_bat_up"] = ([poke(game1, place(0x01, (0x50, 0x20), items))], [0, 7], [0])
    moments["bat_down"] = ([poke(game1, place(0x01, (0x50, 0x20), [(0xCB, 0x60, 0x30, 6)]))], [0], [0])
    moments["carry_sword"] = ([poke(game1, place(0x01, (0x50, 0x30), [(0xB6, 0x51, 0x30)],
                                                 {0x9D: 0x09 * 9, 0x9E: 1, 0x9F: 0}))], [0], [0])
    moments["bridge"] = ([poke(game1, place(0x04, (0x80, 0x30), [(0xBC, 0x40, 0x40)]))], [0], [0])
    moments["dark_maze"] = ([poke(game1, place(0x13, (0x50, 0x30)))], [0], [0])
    dot_room = int(game2[0xA1 - 0x80])
    beside_the_dot = (int(game2[0xA2 - 0x80]) + 10, int(game2[0xA3 - 0x80]) + 4)
    moments["dot_room"] = ([poke(game2, place(dot_room, beside_the_dot))], [0], [0])
    moments["secret_room"] = ([poke(game2, place(0x1E, (0x30, 0x20), extra={0xE5: 0x40})),
                               poke(game2, place(0x1E, (0x30, 0x20), extra={0xE5: 0x90}))], [0, 1], [0, 1])
    moments["black_gate_half"] = ([poke(game1, place(0x10, (0x50, 0x20), extra={0xCA: 0x10}))], [0], [0])
    chalice_home = poke(game1, place(0x12, (0x50, 0x20), [(0xB9, 0x52, 0x20)], {0xDE: 0xFF}))
    moments["win"] = ([chalice_home] * 2, [0, 120], [0, 1])
    walk = [poke(game1, place(0x01, (0x40 + k, 0x30))) for k in range(14)]  # walking right: side view, stride
    moments["walk_right"] = (walk, list(range(14)), [13])
    walk_up = [poke(game1, place(0x01, (0x40, 0x30 + k))) for k in range(14)]   # walking up: back view
    moments["walk_up"] = (walk_up, list(range(14)), [13])
    return moments


# ---- rendering + hashing ------------------------------------------------------------------------------

def digest(img: Picture) -> str:
    return hashlib.sha256(np.ascontiguousarray(img, np.uint8).tobytes()).hexdigest()[:16]


def render_all() -> tuple[dict[str, str], dict[str, Picture], set[str]]:
    _, title, game1 = boot(1)
    _, _, game2 = boot(2)
    game = Game()
    out: dict[str, str] = {}
    screens: dict[str, Picture] = {}
    public: set[str] = set()
    every_pairing = [(cast_key, world_key) for cast_key in content.casts(examples=True)
                     for world_key in content.worlds(examples=True)]
    for look_key in {**looks.LOOKS, **looks.TEMPLATE_LOOKS}:
        for cast_key, world_key in every_pairing:
            look_name, hashes, pictures = render_look(game, look_key, cast_key, world_key,
                                                      scenarios(game1, game2, title), game1)
            if not (content.is_private(cast_key) or content.is_private(world_key)):
                public.add(look_name)
            out.update(hashes)
            screens.update(pictures)
    return out, screens, public


def render_look(game: Game, look_key: str, cast_key: str, world_key: str, moments: dict[str, Scenario],
                game1: RamView) -> tuple[str, dict[str, str], dict[str, Picture]]:
    """One look with one cast in one world, in every moment and halfway through a room scroll:
    (the look's name, the hashes, the screens)."""
    def make_look() -> RoomLook:
        return looks.make(look_key, cast_key, world_key, game.reader)  # fresh: no state carried over
    look_name = make_look().key
    hashes: dict[str, str] = {}
    pictures: dict[str, Picture] = {}
    for name, (rams, frames, keep) in moments.items():
        look = make_look()
        for index, (ram, frame_no) in enumerate(zip(rams, frames)):
            img = look.draw(game.state(ram), frame_no)
            if index in keep:
                key = f"{look_name}/{name}/{index}"
                hashes[key], pictures[key] = digest(img), img
    img = halfway_scroll(make_look(), game, game1)
    key = f"{look_name}/scroll_down/16"
    hashes[key], pictures[key] = digest(img), img
    return look_name, hashes, pictures


def halfway_scroll(look: RoomLook, game: Game, game1: RamView) -> Picture:
    """A room scroll, halfway: old room and new room both drawn without actors, the hero carried across."""
    leaving = game.state(poke(game1, place(0x11, (0x50, 0x0F))))
    arriving = game.state(poke(game1, place(0x02, (0x50, 0x69))))
    scroll = TR.Scroll.between(look, leaving, arriving, 0)
    assert scroll is not None   # the two rooms are next to each other: there is a scroll
    img = scroll.frame()
    for _ in range(15):
        img = scroll.frame()
    return img


def split(hashes: dict[str, str], public: set[str]) -> tuple[dict[str, str], dict[str, str]]:
    """(hashes with public packs, hashes with private packs)."""
    pub = {key: value for key, value in hashes.items() if key.split("/")[0] in public}
    return pub, {key: value for key, value in hashes.items() if key not in pub}


def main() -> int:
    hashes, screens, public = render_all()
    pub, priv = split(hashes, public)
    if "--update" in sys.argv:
        with open(HASHES, "w") as f:
            json.dump(pub, f, indent=1, sort_keys=True)
        if priv:
            with open(PRIVATE_HASHES, "w") as f:
                json.dump(priv, f, indent=1, sort_keys=True)
        print(f"golden: {len(pub)} public + {len(priv)} private reference hashes written")
        return 0
    ref = {}
    for path in (HASHES, PRIVATE_HASHES):
        if os.path.exists(path):
            with open(path) as f:
                ref.update(json.load(f))
    rendered_looks = {key.split("/")[0] for key in hashes}
    ref = {key: value for key, value in ref.items() if key.split("/")[0] in rendered_looks}
    bad = [k for k in sorted(ref) if hashes.get(k) != ref[k]]
    missing = [k for k in sorted(hashes) if k not in ref]
    if bad:
        from PIL import Image
        os.makedirs(FAIL_DIR, exist_ok=True)
        for k in bad:
            if k in screens:
                Image.fromarray(screens[k]).save(os.path.join(FAIL_DIR, k.replace("/", "__") + ".png"))
    print(f"golden: {len(ref) - len(bad)}/{len(ref)} match" + (f"; DIFFER: {bad}" if bad else "")
          + (f"; new (not in reference): {missing}" if missing else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
