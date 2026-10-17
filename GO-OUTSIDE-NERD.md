# Go outside, nerd

The deep end: the technical details behind Adventure Forever that the [architecture guide](docs/ARCHITECTURE.md)
doesn't need - which ROMs work, how faithful the emulation is, how the memory is sampled, and how the speed is
kept. For how the code fits together (the folders, one frame, looks, casts and worlds), start there.

```
 your ROM ──▶ emulator (Stella) ──▶ 128 bytes of RAM ──▶ GameState ──▶ look + cast + world ──▶ 256x240 picture
                    ▲                                                                                │
                    └──────────────── joystick ◀── the window (keys, views, music, recording) ◀───────┘
```

## Which ROM

Every good dump of the NTSC cartridge is the same 4096 bytes (MD5 `157bddb7...`), so "different
dumps" isn't a problem. A different *version* (the PAL release, a hack) could keep its tables or RAM elsewhere,
so at startup `engine/versions.py` names the ROM by its hash and checks our RAM map against its object
table. If anything doesn't match, the game still runs, and the overlay says what moved, so the remasters
drawing wrongly is never a mystery.

(Why the ROM's tables are read from your copy rather than kept in the code: [the architecture guide](docs/ARCHITECTURE.md#why-it-works-this-way).)

## Accuracy

- **The emulation is Stella's, untouched.** We load the Stella libretro core and the original ROM, both
  unmodified - the same Stella commit (`b52ccb02e`) on every platform, built by this repository's workflow
  and checksum-verified by `tools/get_core.py`. Stella emulates the CPU and TIA cycle by cycle, and every
  collision, dragon move and bat theft is the real game code. The "2600" pane is Stella's own output.
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

More: [platform rules](docs/platform-rules.md), [reading the RAM view](docs/reading-the-ram.md).
