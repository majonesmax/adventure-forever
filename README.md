# Adventure Forever

Atari 2600 **Adventure** (Warren Robinett, 1980) running *unmodified* in an emulator, with every frame
redrawn live from the game's 128 bytes of RAM, in two new **looks**:

- **NES**: an 8-bit remaster.
- **SNES**: a 16-bit remaster.

Who's in the game and where it happens come in **packs**, and any look shows any of them:

- **classic**: a knight, three dragons, the bat and the chalice, in brick and stone castles.
- **pbj**: PBJ in her bear-ear hat, Alice the Scottish terrier, who stretches into a bridge, a Yeti, a
  giant hen and a swamp Bog for dragons, a magpie that steals things, and the Storybook to bring home, in
  candy, ice and fire kingdoms.

You can mix them: the knight in the candy kingdom, PBJ in the brick castles, either on either console.

The original 2600 picture can run alongside, and a four-way grid shows the NES and SNES looks, the
original, and the game's live RAM at once (**[how to read the live RAM view →](docs/reading-the-ram.md)**).
Gameplay is 100% the original: the emulator runs the real
game, and the remasters only *draw* it.

## How it works

The 2600 has no screen memory; Adventure's whole world lives in 128 bytes of RAM: which room each object is
in, where, what you carry, what each dragon is doing. Every frame we read that RAM through the libretro API
and draw our own picture from it, using the ROM's own room and object tables (decoded at run time from your
ROM). So the remasters can't change how the game plays. Room-to-room scrolls pause the emulator while they
slide, so the game's timing is untouched too.

| Folder | What's in it |
|---|---|
| `engine/` | the game itself: the emulator, the game's state (`GameState`), the RAM map and ROM tables, the music |
| `looks/` | how it's drawn (the consoles): the look contract (`base.py`), the NES and SNES looks, a template |
| `content/` | what's drawn: casts (who) and worlds (where), loaded from packs |
| `packs/` | the packs: `pack.json`, `cast/` pictures and `world/` tiles each (`classic`, `pbj`, `template`) |
| `app/` | the window: views, room scrolls, recording, the live RAM panel |
| `shared/` | pixel-art helpers, palettes, the pixel font |
| `tools/` | the art pipeline, the video editor, viewers |
| `tests/` | checks against the real emulator, including pixel-exact "golden" tests of every look |

**[How it all fits together →](docs/ARCHITECTURE.md)** (or the one-page version: [SHUT-UP-NERD.md](SHUT-UP-NERD.md))

## Running it (macOS, Apple Silicon)

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
tools/get_core.sh                          # downloads the Stella libretro core into cores/
cp /path/to/adventure.a26 roms/            # your own ROM (4096 bytes)
.venv/bin/python play.py                   # or: play.py --look snes --cast classic / --grid / --list / --help
```

Without `roms/adventure.a26`, the game asks for the ROM once in a Finder dialog and remembers it.

**Keys:** arrows + space = joystick, Tab = game select (games 1–3), Enter = reset/start,
**L** = look (NES → SNES), **C** = cast, **W** = world (classic → pbj → yours; an overlay names
what's on screen; **I** shows it any time),
**V** = view (side by side → remaster only → 2600 only → grid),
T = room scrolls on/off, M / − / = = music on/off and volume, N = next music source, S = screenshot,
R = record, P = pause, Esc = quit.

`package/build_app.sh` builds a standalone macOS app (`Adventure Forever.app`).

## Music

By default the game plays five original songs from `chiptune.py` (title, overworld, dungeon, final, win),
synthesised NES-style. To use your own, create `music/music.json` mapping areas to an NSF track or a WAV
file:

```json
{"title": {"nsf": "music/my.nsf", "track": 1}, "overworld": {"file": "music/overworld.wav"}}
```

Areas not listed fall silent; N switches between your config and the built-in songs.
`python -m engine.music --survey FILE.nsf` lists an NSF's tracks; NSF playback needs
`brew install game-music-emu`.

## Make your own look or cast

A **look** is the console: how the game is drawn (its colour rules, status bar and screens). A **cast** is
who's in the game, a **world** is where it happens; a **pack** is a folder of pictures with a cast, a world or
both. Any look shows any cast in any world, adapting the pictures to its own rules
([platform rules](docs/platform-rules.md)). Each has a small working example to run and copy:

- **A new pack** (your own heroes, villains, items and scenery, no code needed): copy `packs/template` to
  `private/packs/<name>` (git-ignored, so it stays yours) or `packs/<name>`, then `play.py --pack <name>`.
  **[Making a pack →](docs/making-a-pack.md)**
- **A new look** (an Amiga look, a C64 look...): start from `looks/template_look.py`
  (`play.py --look template`). **[Making a look →](docs/making-a-look.md)**

## Recording and making videos

R records every look (with the cast and world on screen) plus the 2600 picture as separate lossless videos, the audio as heard, and a
per-frame log of what happened (rooms, pickups, dragon fights, deaths, wins). `tools/make_video.py` cuts a take
into a 1080p video from an `edit.json` you write per take (ranges to keep, captions, cards); see its
docstring. Needs `ffmpeg`.

## How this was made

This project was built with generative AI. Most of the code was written with Claude (Anthropic), working
with a human who played, tested and directed it.

All the art is pixel art kept as text in each pack's `source/` folder (one character per pixel), so it can be
read, edited and compared like code. Most of it was drawn that way from the start: PBJ and friends, the
knight, the items, the bat and the bridge, while the pbj world's kingdoms are painted by code. Three things
began as Stable Diffusion XL images, then were reduced to a few colours and converted to text art: the
classic world's wall and floor tiles, the dragons' shapes, and the pbj world's grass. The music is written
as notes in code.

## Credits and license

- **Adventure** © 1980 Atari, created by Warren Robinett. Not included: bring your own ROM. His hidden
  credit is shown faithfully, in the original's own graphic and colours.
- **Stella** emulator core (GPL-2.0), downloaded separately: https://github.com/stella-emu/stella
- Code: MIT (`LICENSE`). Original art and music: CC BY 4.0 (`LICENSE-ASSETS.md`).

A non-commercial fan project, not affiliated with or endorsed by Atari, Nintendo or anyone else.
