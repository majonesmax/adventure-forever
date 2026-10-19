# Working on Adventure Forever with an AI assistant

Notes for Claude Code (or any coding assistant) working in this repository. People: the same notes are a
quick tour.

Atari 2600 *Adventure* runs unmodified in the Stella emulator; every frame, the game's 128 bytes of RAM are
read and the scene is redrawn. How it fits together: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## The words

- **look**: the console - colour rules, status bar, title and win screens (`looks/`: nes, snes, vga, paper).
- **cast**: who - hero, dragons, bat, items, bridge, messenger, the win lines.
- **world**: where - each place's walls, floor and gates, names, title word, soundtrack.
- **pack**: a folder with a cast and/or a world (`packs/`, `private/packs/`, or folders in `ADVENTURE_PACKS`).

Any look shows any cast in any world. Keep it that way: a look never knows about a particular pack, and a pack
never assumes a particular look.

## Commands

```sh
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
python tools/get_core.py                    # the pinned Stella core, checksum-verified
python play.py --pack <pack> --look <look>  # play (the user's ROM is roms/adventure.a26)
python play.py --list                       # every look and pack
python tools/preview.py --pack <pack>       # the pack in every look, as one PNG - look at it
python tests/golden.py                      # every look x cast x world still draws the same pixels
python tests/test_controls.py               # every key is documented
python tools/readability.py                 # no file got harder to read (and FILE... lists a file's issues)
pyright                                     # the type hints check out (pyrightconfig.json)
python -m engine.ambience                   # the worlds' sounds (summer, woods, cave...) as WAVs in shots/ambience/
python -m engine.effects                    # each look's sound effects as WAVs in shots/effects/
python -m engine.orchestra                  # the songs on the SNES's band (soundcard: VGA, toybox: paper) in shots/music/
python play.py --check                      # the app plays itself for a few seconds and says whether it works
gh workflow run downloads.yml               # GitHub builds the Windows and macOS downloads (and runs --check)
git tag v1.3 && git push origin v1.3        # ...and a v* tag makes the release (notes: package/release-notes/)
```

## Rules

- **Never change the game.** No ROM patches, no RAM writes during play. Looks only read a `GameState`.
- **Draw things where the game has them.** Hits, pickups and walls come from the game's own positions; a
  sprite moved for looks makes the picture lie.
- **Never commit** the ROM, emulator cores, `private/`, `STATE.md`, or anything from the ROM (its tables are
  read from the user's copy at startup).
- **Prove nothing else moved.** Run `tests/golden.py` after any change to `looks/`, `content/` or `shared/`. If
  only what you meant to change differs, `--update` it, and say what changed.
- **Look at your work.** After changing art, a world or a look, run `tools/preview.py` and read the PNG before
  saying it's done.
- **Art is text.** Sprites are drawn as text art in a pack's `source/*.py` (one character a pixel, see
  `shared/pixelart.py`) and generated into `cast/`. Don't hand-edit the PNGs; edit the source and rerun it.
- **Public packs are original.** No names, logos, likenesses, quotes or exact designs from someone else's
  work. Inspired-by is fine; a copy is not. Fan art of real shows belongs in `private/packs/`.

## Readable code

The person who owns this code reads it rather than writes it, and isn't a Python specialist. Write for them:

- **Names say what things are.** `state`, not `st`; `look`, not `lk`; `object_number`, not `n`. Short names
  only for loop counters and coordinates (`i`, `x`, `y`, `dx`, `w`, `h`).
- **One idea per line.** Don't put a calculation inside a call inside an assignment; name the steps.
- **Name the numbers.** `224 - 2 * y` needs a name or a comment saying what 224 is.
- **No conditional expression inside another expression**, and a loop instead of a comprehension that needs
  more than one `if`.
- **Short functions:** about 40 lines at most, with few branches.
- **Types on every signature.** `def draw(self, state: GameState, frame_no: int) -> Picture`. The plain
  names for arrays and sounds are in `shared/types.py` (Picture, Mask, Floats, Samples, Rgb, Point,
  Instrument); records are `typing.NamedTuple`s with a typed field per line. pyright checks them, and ruff
  (ANN rules) flags any function left without them.
- Lines up to 110 characters.

`tools/readability.py` checks what a tool can (ruff.toml's rules, names under 3 letters, and pyright's type
errors). Every file is at zero (`tools/readability_baseline.json`); keep it there. The Claude Code hook in
`.claude/settings.json` runs it after every edit and hands back anything new - fix it before moving on.
Refactors are safe: `tests/golden.py` proves every picture stays the same. GitHub runs the same checks on
every push (`.github/workflows/checks.yml`): ruff, pyright and readability.py, all must pass.

## Style

Match the code around you: short modules with a docstring saying what they are, plain names, comments that
say why. Docs are plain English for people - short sentences, no hype words, no "simply". When adding a key,
add it to `app/controls.py`; the help panel and both READMEs follow from there.

## Guides

[Making a pack](docs/making-a-pack.md) · [making a look](docs/making-a-look.md) ·
[platform rules](docs/platform-rules.md) · [reading the RAM view](docs/reading-the-ram.md) ·
[Go outside, nerd](GO-OUTSIDE-NERD.md) (accuracy and timing)
