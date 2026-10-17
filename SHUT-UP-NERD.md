# Shut up, nerd: how Adventure Forever works

The real Atari 2600 *Adventure* runs, untouched, in an emulator. We never draw what the 2600 draws. Every
frame we read the game's memory and draw the scene again, our way.

```
 your ROM ──▶ emulator (Stella) ──▶ 128 bytes of RAM ──▶ GameState ──▶ look + cast + world ──▶ 256x240 picture
                    ▲                                                                                │
                    └──────────────── joystick ◀── the window (keys, views, music, recording) ◀───────┘
```

## Two kinds of game data

| | **RAM** (128 bytes) | **ROM** (4 KB, your file) |
|---|---|---|
| What | everything that **changes**: your room and position, every object's room, position and state, what you carry, gates opening, the win | everything that **never changes**: each room's wall layout, colour and exits; each object's size, colour and graphics |
| Read | every frame | once, at startup |
| By | `engine/state.py` turns it into a `GameState` (named fields, no addresses) | `engine/rooms.py`, `engine/objects.py` decode its tables |

**Which ROM.** Every good dump of the NTSC cartridge is the same 4096 bytes (MD5 `157bddb7...`), so "different
dumps" isn't a problem. A different *version* (the PAL release, a hack) could keep its tables or RAM elsewhere,
so at startup `engine/versions.py` names the ROM by its hash and checks our RAM map against its object
table. If anything doesn't match, the game still runs, and the overlay says what moved, so the remasters
drawing wrongly is never a mystery.

The ROM's tables aren't copied into our code on purpose. They're Atari's data, so we read them from your copy
and the repository stays free of it. What we *do* keep is knowledge about the game: which RAM address means
what (`engine/ram_map.py`) and where the tables live in the ROM.

## Four nouns

| | What | Examples | Code | Key |
|---|---|---|---|---|
| **look** | the console: colour rules, status bar, title and win screens | NES, SNES, VGA | `looks/` | L |
| **cast** | who: hero, dragons, bat, items, bridge, messenger, the win message | the knight, PBJ and friends | `content/cast.py` | C |
| **world** | where: what each of the game's places is made of (walls, floor, gates), and what it's called | brick castles, candy kingdoms | `content/world.py` | W |
| **pack** | a folder holding a cast, a world, or both | `packs/classic`, `packs/pbj` | `content/pack.py` | |

Any look shows any cast in any world. The look adapts the pictures to its rules once, up front:
`adapt()` for sprites, `adapt_scenery()` for rooms and gates. NES snaps to the NES palette; SNES uses 15-bit
colour plus soft outlines. Anything a cast or world leaves out is drawn as the original 2600 graphic. **I**
shows which three are on screen.

## One frame (`app/window.py`)

1. Keys: arrows and space become the joystick; letters are window commands.
2. The emulator runs one frame of the real game (paused while a room scroll slides).
3. RAM → `GameState` → the look draws it (`RoomLook.draw` in `looks/base.py`):
   - the world's room, then the objects where the game has them, then the hero (his facing worked out from
     his movement), then the held item;
   - torch light in dark rooms, the status bar, and the win screens.
4. Music follows the area; the recorder saves every look's picture, the audio and a log.
5. Show: one look, side by side with the 2600, the 2600 alone, or the grid: what you're playing over a
   comparison (the next look with the same cast and world, or its own via Shift+L / C / W), the 2600 and live RAM.

## Rules that never break

- **The game is never changed.** We only read its memory.
- **Draw things exactly where the game has them.** Hits and pickups use the game's own small shapes; nudging a
  sprite once made sword hits look wrong.
- **The game decides where walls are.** A world only decides what they're made of.
- **The game's timing is sacred.** Scrolls pause the emulator; no frames are added or skipped.

## Accuracy (for emulation people)

- **The emulation is Stella's, untouched.** We load the Stella libretro core and the original ROM, both
  unmodified - the same Stella commit (`b52ccb02e`) on every platform, built by this repository's workflow
  and checksum-verified by `tools/get_core.py`. Stella emulates the CPU and TIA cycle by cycle, and every collision, dragon move and bat theft is
  the real game code. The "2600" pane is Stella's own output.
- **Sampling: once per emulated frame (60 Hz).** `retro_run()` emulates one whole TV frame and stops. We then
  read the 128 RAM bytes through libretro's memory API: a pointer outside the emulated bus, so it costs zero
  cycles and has no side effects. We copy them and draw from the copy. Adventure reads the joystick and runs
  its logic once per frame, so the frame boundary is where the state is complete: sampling faster would catch
  half-updated state, and slower would miss frames. We never write RAM during play (only the tests do, to set
  up scenes).
- **Speed:** exactly the game's own, paced by us, not the emulator - see [Timing](#timing) below.
- **Verified, not assumed.** `tests/verify_render.py` rebuilds the 2600 picture purely from our RAM snapshots
  and compares it with Stella's: 372 frames, 34 differing by 191 pixels in total (a known baseline), the rest
  exact. `verify_ram`, `verify_rooms` and `verify_exits` check the address map, walls and exits against the
  running game.
- **Known deviations, all presentation:**
  - room scrolls pause the emulator while they slide; no frame is skipped or doubled, and **T** turns them off;
  - the remasters don't flicker (we know every object's position, so we draw them all every frame); the 2600
    pane still flickers authentically;
  - pacing follows your display's 60 Hz vsync, or a timer, and the core runs at 60.0 fps;
  - the joystick is passed in before each frame, as the 2600 polls once per frame; vsync adds the usual frame or
    so of display delay;
  - the music is added on top, and the game's own sound comes from Stella unchanged.

## Timing

**The emulator never runs by itself.** We register its callbacks once, at startup. Then each call to
`retro_run()` means "emulate one frame and come back": Stella runs the CPU and the TIA's beam cycle by cycle
through one whole TV frame, calling us back *during* that call ("what's the joystick doing?", "here's the
picture", "here's the sound"), and returns - in about a millisecond. Between calls it is frozen. So the
emulator decides what happens in a frame (always 1/60 s of the game's time); **we decide when the next
frame happens.**

```
 our loop:  keys -> retro_run() ~1 ms -> read RAM -> draw the looks -> show (flip) -> wait -> again
                   (callbacks fire inside)                                  └─ vsync or timer: ~16.7 ms a lap
```

Three clocks, and who follows whom:

| Clock | Rate | What we do with it |
|---|---|---|
| **The game** | 60.0 frames a second (the core's; a real NTSC 2600 is ~59.92) | one `retro_run()` per lap, never skipped, never doubled |
| **Your display** | its refresh rate | at ~60 Hz, vsync paces the loop: one game frame per refresh, no tearing. Anything else (120/144 Hz, or PAL's 50 Hz game), or no vsync: a timer paces it, so a fast screen never means a fast game |
| **Your sound card** | its own exact rate, never quite the display's | a small buffer absorbs the drift; the debug line counts samples `missing` / `dropped` if it ever runs dry or overflows |

- **Check it yourself:** the startup line says what was chosen (`display 60 Hz, vsync on, pacing by vsync`),
  and the debug line (**D**) shows the measured game speed.
- **Slower, never skipped:** if a lap takes longer than 1/60 s (a weak machine, the grid while recording), the
  game slows down rather than skipping frames, so the game's world and the picture stay one-to-one.
- **Pauses are free:** P and room scrolls simply don't call `retro_run()`; the game sees no time pass.
- **The 0.13%:** at 60.0 instead of ~59.92 fps we're about 5 seconds an hour faster than a 1980 TV, as
  RetroArch is on a 60 Hz screen.

## Where things live

| Folder | |
|---|---|
| `engine/` | the game: emulator, `GameState`, RAM map, ROM decoders, 2600 palette, music |
| `looks/` | the consoles: `base.py` (the contract + all the placing), `nes/`, `snes/`, `template_look.py` |
| `content/` | casts, worlds, packs, and finding them |
| `packs/` | the packs: `pack.json`, `cast/` pictures, `world/` tiles, `source/` (all art as text, one character a pixel) |
| `shared/` | room layout geometry, pixel-art helpers, palettes, the pixel font |
| `app/` | the window: views, room scrolls, the RAM panel, the overlay, the help panel (H; every key is in `controls.py`), recording |
| `tools/` | video editor, grid GIF maker (`make_gif.py`), 2600-picture rebuild, RAM viewer, emulator core download |
| `package/` | `build.py`: the download for the system it runs on (app + README + licences, Stella's GPL source link) |
| `tests/` | checks against the real emulator; `golden.py` renders every look × cast × world and compares hashes |

Not in the repository: your ROM, the emulator core (`tools/get_core.py`), and `private/` (personal packs,
personal music, the old AI art tools).

## Extend it

- **New pack** (no code): `cp -r packs/template private/packs/mine`, swap the pictures, `play.py --pack mine`.
  See [docs/making-a-pack.md](docs/making-a-pack.md).
- **New look** (a C64, a Game Boy...): copy `looks/template_look.py`, add it to `LOOKS`. See
  [docs/making-a-look.md](docs/making-a-look.md).
- **Prove nothing broke:** `tests/golden.py` (`--update` after a deliberate change).

Deeper: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [platform rules](docs/platform-rules.md),
[reading the RAM view](docs/reading-the-ram.md).
