# How Adventure Forever works

The real Atari 2600 game runs, untouched, inside an emulator. Everything you see is redrawn from the game's
memory, every frame. Nothing here changes how the game plays; it only changes how it *looks*.

```
 ┌──────────────────────┐   128 bytes of RAM    ┌──────────────────────┐   GameState   ┌──────────────────────┐
 │ engine/emulator.py   │ ────────────────────▶ │ engine/state.py      │ ────────────▶ │ looks/ + content/    │
 │ the Stella core runs │      every frame      │ room, hero, objects, │               │ a look (NES, SNES…)  │
 │ the real game        │                       │ carried item, won... │               │ shows a cast+world   │
 └──────────▲───────────┘                       └──────────────────────┘               └──────────┬───────────┘
            │ joystick                                                                  256x240   │
 ┌──────────┴──────────────────────────────────────────────────────────────────────────────────── ▼ ──────────┐
 │ app/ - the window: keys, views (side by side, grid), room scrolls, music, recording, the live RAM panel     │
 └─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Why it works this way

The 2600 has no screen memory: the game draws each line of the TV picture as the beam passes. But its whole
world (which room every object is in, where, what you carry, what each dragon is doing) lives in 128 bytes of
RAM, in well-defined places (`engine/ram_map.py`, decoded from the game's commented disassembly and checked
against the running game by `tests/verify_ram.py`). Read those bytes and you know everything needed to draw
the scene your own way.

**RAM and ROM.** RAM holds everything that changes (positions, rooms, states, what you carry) and is
read every frame. The ROM holds everything that doesn't (each room's walls, colour and exits; each object's
size and graphics). `engine/rooms.py` and `engine/objects.py` decode it once at startup, from *your* copy:
those tables are Atari's data, so they are deliberately not copied into this repository. What the code
keeps is knowledge *about* the game: what each RAM address means and where the tables are in the ROM.

Rules every look follows:

- **Never change the game.** The emulator runs the original ROM; looks only read state.
- **Draw things where the game has them.** Hits, pickups and walls are decided by the game's own positions.
  Moving a sprite for looks (an early experiment nudged the held sword clear of the hero) makes the game
  disagree with the picture: the sword missed where it looked like it hit.
- **The game's timing is sacred.** Room scrolls pause the emulator while they slide; no frame is skipped or
  added to the game itself.

## The folders

| Folder | What's in it |
|---|---|
| `play.py` | the entry point: command-line options, then the window |
| `engine/` | **the game itself.** `emulator.py` (the libretro core), `state.py` (`Game`, `GameState`), `ram_map.py` / `rooms.py` / `objects.py` (what the RAM and ROM tables mean), `palette.py` (the 2600's colours), `music.py` + `chiptune.py` (background music), `paths.py` (where files live) |
| `looks/` | **how the game is drawn: the consoles.** `base.py` defines what a look is ([making a look](making-a-look.md)); `nes/` and `snes/` are the two built-in looks; `template_look.py` is the smallest complete look; `__init__.py` lists them |
| `content/` | **what's drawn.** `cast.py` (who: hero, dragons, items...), `world.py` (where: the game's places, their walls, floors, gates and names), `pack.py` (a folder with a cast and/or a world), `__init__.py` (finds the packs) - [making a pack](making-a-pack.md) |
| `packs/` | **the packs**, one folder each: `pack.json`, `cast/` pictures, `world/` tiles, and the text art they were drawn from in `source/`. `classic` (the NES look's own), `pbj` (the SNES look's own), `template` (the smallest). Your own go in `private/packs/` |
| `app/` | **the window around the game.** `window.py` (the frame loop, views, keys), `transitions.py` (room scrolls), `recorder.py` (gameplay recording), `debug_panel.py` (the live RAM view: [reading it](reading-the-ram.md)), `rom.py` (finding your ROM) |
| `shared/` | helpers used by looks, content and the app: `layout.py` (the screen and room layout, where the walls are in pixels), `pixelart.py` (sprites drawn as text, pasting), `palettes.py` (the NES palette), `hud.py` (the pixel font) |
| `tools/` | development tools: the emulator core download (`get_core.py`), the video editor (`make_video.py`), the grid GIF maker (`make_gif.py`), the 2600-picture rebuild (`rebuild_2600.py`), the RAM viewer, mock-ups |
| `tests/` | checks against the real emulator; `golden.py` proves every look still draws exactly the same pixels |

## One frame, in order (`app/window.py`)

1. **Input:** arrows and space become the joystick; other keys are window commands (L, C, W, V, R...). Every key
   is listed once, in `app/controls.py`: the help panel (H) draws it, and `tests/test_controls.py` checks the READMEs
   list the same keys.
2. **The game:** one emulator frame, unless paused or a room scroll is sliding.
3. **Pictures:** `Game.state(ram)` snapshots the RAM into a `GameState`; each look that's on screen (all of
   them while recording) draws it. When the hero walks into another room, a `Scroll` slides the old room out
   and the new one in.
4. **Extras:** the music follows the area (title, overworld, dungeon, final, win); the recorder saves every
   look's picture, the audio and a log; the RAM panel logs events.
5. **Show:** the current view is assembled and flipped to the screen. Vsync or a timer paces the loop at the
   game's 60 frames a second - the emulator has no clock of its own ([timing](../SHUT-UP-NERD.md#timing)).

## Looks, casts and worlds

Three separate things meet on screen:

- a **look** is the console: its colour rules, its status bar and screens (`looks/`);
- a **cast** is who's in the game: hero, dragons, bat, items, bridge, messenger, the win message (`content/cast.py`);
- a **world** is where: what each of the game's places is made of (walls, floor, gates), and what it's called (`content/world.py`).

Casts and worlds come in **packs** (folders in `packs/` and `private/packs/`). Any look shows any cast in any
world: when a look is made, it passes the cast's pictures through its `adapt()` and the world's rooms and
gates through its `adapt_scenery()` (NES colours; SNES 15-bit colour and soft outlines), once. "Author rich,
platforms reduce."

```
 packs/pbj/cast/hero_down_0.png ─▶ Cast  ─▶ SnesLook.adapt()          ─▶ RoomLook places it where the game has the hero
 packs/classic/world/wall_*.png ─▶ World ─▶ SnesLook.adapt_scenery()  ─▶ RoomLook draws it where the game has walls
```

The game decides where walls are; a world only decides what they're made of, by place (`meadow`,
`gold_castle`, `labyrinth`, `catacombs`... - the game's own regions, so they mean the same in every world).
Whatever a cast or world leaves out is the original 2600 graphic. What each look enforces and uses:
[platform rules](platform-rules.md).

| | A new **look** | A new **pack** (cast and/or world) |
|---|---|---|
| What changes | how everything is drawn: colour rules, status bar, title and win screens | who's in it and where: characters, items, scenery, names |
| You write | a class: `RoomLook`'s console methods (or a whole `Look` for a different layout) | pictures and a `pack.json` - no code (a `cast.py` / `world.py` for tricks) |
| Start from | `looks/template_look.py` | `packs/template/` |
| Guide | [making a look](making-a-look.md) | [making a pack](making-a-pack.md) |

## Checking your changes

```sh
python tests/golden.py          # every look, with every cast in every world, draws the same pixels
python tests/verify_ram.py      # the RAM map matches the running game
python tests/verify_rooms.py    # the walls decoded from the ROM match the real picture
python tests/verify_exits.py    # walking off each edge leads where rooms.py says
python tests/verify_render.py   # the rebuilt 2600 picture matches the emulator's
python tests/test_controls.py   # every key the window handles is in the help panel and both READMEs
```

`golden.py --update` accepts new pictures when you change a look on purpose. These checks need your ROM and
the emulator core, so they run on your machine.
