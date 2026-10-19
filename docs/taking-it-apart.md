# How we took Adventure apart

This is the story of how the Atari 2600 *Adventure* (Warren Robinett, 1980) was worked out, before and while
the remaster was written: what we started from, the tools and why each one, what went wrong, and what we
ended up knowing. The detail lives in the code and the other pages; this one ties them together.

The work was done by Claude (an AI model, working in Claude Code) at the direction of the project's owner.
Most of it happened in one day, 13 October 2026, as the first steps of the project; a few pieces came later,
when a feature needed them. Its sister project, [Haunted House remastered](https://github.com/majonesmax/haunted-house-remastered),
went through the same process with more tools, and its [story](https://github.com/majonesmax/haunted-house-remastered/blob/main/docs/taking-it-apart.md)
goes further. Adventure came first.

## The question

Could a 2600 game be redrawn as a new game, live, without changing a byte of it? The idea: run the real game
in an emulator, read its memory after every frame, and draw the scene our own way.

Adventure looked like a good first try, for three reasons.

- **The 2600 has no screen memory.** It draws the picture line by line as the TV's beam moves, from whatever
  is in its registers. So there's no picture in memory to reverse-engineer, only the game's own state.
- **That state is small and meaningful.** The whole game lives in 128 bytes of RAM, and in Adventure those
  bytes are mostly plain facts: which room each object is in, where it is, what you carry, what each dragon
  is doing.
- **The world is small.** 30 rooms of coarse walls and 19 numbered objects, all in a 4 KB ROM.

Re-drawing from RAM also removes the original's flicker for free: the 2600 can only draw two objects a frame
and takes turns, but we know where all of them are.

## Where we started

The ROM, and Joel D. Park's commented disassembly of it, as converted by Andy McFadden
([6502disassembly.com](https://6502disassembly.com/2600-adventure/)). Adventure is one of the best-studied
2600 games, so a lot of this is public knowledge: the object list, the room list, the dragons' code. The
disassembly names Robinett's own structures - the "object list" and the "room list" - and most of the routines.

We used it as a map, and checked everything it said in the running game instead of taking it on trust. That
habit found one real mistake in it (below).

## The method

One loop, over and over:

> **Read the code, write down what you think it means, predict what the running game will do, and check.**

Each check is a small program that plays the real game in the emulator with no window, so it can visit every
room or walk out of every exit, and run again after each correction. The checks stayed in the project
(`tests/verify_*.py`), so every claim here can be proved again with one command.

## The tools, and why each one

**A RAM viewer** (`tools/ram_viewer.py`). The project's first tool: the raw emulator with a live panel of
the 128 bytes beside it. Move the hero and watch which bytes change. It's the quickest way to match a byte
to a meaning, and the starting point for every guess. (The game's grid view later got a much richer version:
[reading the RAM view](reading-the-ram.md).)

**The RAM map, checked claim by claim** (`engine/ram_map.py`, `tests/verify_ram.py`, 11 checks). Start
game 1 and compare the object list in RAM with the table the game copies it from in ROM ($F460 for game 1,
$F491 for games 2 and 3). Then walk the hero to the yellow key, pick it up and carry it, checking at each
step: the carried byte is the object's number times 9; the item's position is the hero's plus an offset fixed
when it was picked up; and the item follows one step behind, because the game moves it after the hero.

**Decoders for the rooms and objects** (`engine/rooms.py`, `engine/objects.py`). The room list at $FE1B
gives each room's walls, colour, layout flags and exits. The object table at $FF44 gives each object's
position, its states, its pictures, colour and size. Both are read from your own copy of the ROM every time
the game starts; nothing from the ROM is stored in the project.

**Every room, wall by wall** (`tests/verify_rooms.py`, 23 of 23 visible rooms). Put the hero in each room by
writing its room byte, let the game draw it, and compare every wall cell we decoded with the real frame. This
also measured exactly which scan lines each of the seven wall rows covers. Seven rooms - the catacombs and
the black maze - draw their walls in the background colour, so they can't be seen. With `--reveal`, a patched
**copy** of the ROM gives those rooms black walls, so they can be checked too: 30 of 30. The real ROM is never
touched.

**Every exit, walked** (`tests/verify_exits.py`, 86 of 86 exits in game 1). Place the hero beside each opening
of each room, hold the stick toward it, and read back which room the game took him to. This is the check that
caught the disassembly's mistake.

**A picture of the whole world** (`tools/room_sheet.py`). Every room drawn from the decoded data alone, with
no emulator, as one sheet. A wrong decode usually looks wrong.

**The colours, measured, not copied** (`engine/palette.py`). Published 2600 palettes differ slightly from
each other, and what matters is what this emulator draws. So a patched copy of the ROM swaps the colour the
game loads for the floor (`lda #$08` at $F13C) for each of the 128 colours in turn, and we sample the floor.

**The whole picture, rebuilt from RAM** (`tools/rebuild_2600.py`, `tests/verify_render.py`). The strongest
check: draw the 2600's own picture from our reading of the RAM and the ROM alone, and compare it pixel for
pixel with the emulator's real frame. If our reading were incomplete, it would show. Over a run that visits
every room and plays a short game, 338 of 372 frames match exactly, and the other 34 differ by 191 pixels in
all - each one explained by the 2600's timing (below), so we left them as a known baseline rather than copy
the quirks.

**Which ROM is this?** (`engine/versions.py`). Added later: the game identifies the ROM by its MD5, and if
it isn't the one this was all checked against, it looks for the tables and RAM addresses where we expect
them, and says what doesn't match instead of drawing nonsense.

## What went wrong, and how it was caught

| What happened | What it really was |
|---|---|
| Walking left and right out of rooms didn't match the room table | **The disassembly's comment has the exits' left and right swapped.** Walking every exit proved it, and so does the code: leaving off the right reads byte 6 of the room's entry, which the comment calls its left exit. |
| Seven rooms couldn't be checked | Their walls are drawn in the background colour. A patched copy of the ROM made them visible to the check. |
| Some measured colours came out black at random | The emulator core keeps global state and breaks after being loaded many times in one process. Each colour is now measured in a process of its own. |
| A carried item seemed to lag the hero | A **real rule**: the game moves the item a step after the hero. |
| The thin side walls came out in odd colours on the 2600 | A **hardware accident**: they're the TIA's missiles, coloured by whatever objects share the room. The remaster draws them as walls. |
| The rebuilt picture differed from the real one on a few frames | **Real timing**: the game spreads its work over three frames, some before the picture is drawn (the dragons) and some after (the hero); it draws objects from positions saved a frame earlier; and one object is shifted a line by a TIA delay. Worth knowing, not worth copying. |
| A win sometimes went unnoticed | We asked "is the chalice in the gold castle now?", but the game latches its verdict once: byte $DE becomes $FF on a win and stays until RESET (being eaten leaves it 0). We now read the game's own flag. |
| "What changed since last frame" saw no changes | Our snapshot was a live view of the emulator's memory, so last frame's copy changed too. Each frame now copies the 128 bytes. |
| The sword seemed to miss dragons it was touching | Not the game: a look had drawn the carried sword a few pixels away from where it really was, to keep it clear of the hero. **Never move anything the game hit-tests.** |

## What we know now

- **The RAM:** the hero's room and position (and the last spot that didn't hit a wall, for bouncing back),
  what's carried and its offset, the game number, the win flag, the random seed, the sound playing, and the
  object list - every dragon, item, gate and the bat, with each one's room, position and state. See
  `engine/ram_map.py` and [reading the RAM view](reading-the-ram.md).
- **The world:** all 30 rooms - walls, colours, mirrored or repeated halves, walls in front of objects, thin
  walls, and exits, including those that depend on the game number and the special ones the code handles
  itself (the castle gates, the secret room).
- **The objects:** every object's pictures and states, read from the ROM. The dragons' states come from their
  code: 0 normal, 1 dead, 2 has eaten the hero, 3 and up roaring. The gates' state byte is their height: $1C
  shut, rising quickly to open, lowering over about a second to close.
- **The screen:** where everything is drawn, as formulas (a top line of 224 - 2 × y; objects one pixel left
  of x, the hero two), what's drawn in front of what, and which colours flash (an odd colour number takes its
  colour from a RAM byte, usually the frame counter).
- **The sound:** a counter and a type in RAM say when the game starts each of its six sounds - which the
  remaster uses to play its own versions.

Still open: the bat's carried-object byte isn't in the same form as the hero's, and the PAL cartridge is
recognised but hasn't been checked.

## How this compares with Haunted House

Adventure was the first, and it needed less. Its game state is plain enough that a RAM map, the decoders and
the rebuilt picture were proof enough to draw it. We never had to model the dragons' or the bat's behaviour:
the remaster draws them wherever the game puts them.

Haunted House was harder - less was known about it, and its monsters and sounds are tangled in the code - so
it got more: a tracer of its own for the machine code, models that predict the game frame by frame (the
monsters for 30,000 frames), and sweeps of all nine game variations. If Adventure ever needs that depth (to
explain the bat's choices, say), those tools are the way in.

## Was this an AI doing something a person couldn't?

No. Every method here is one a careful person would use. Two things were different in practice: checks were
cheap enough to cover everything (every room, every exit) instead of sampling, and throwaway tools cost
little, so a question could get a tool of its own. The limits were the usual ones: first guesses were often
wrong, and the checking - not the reading - is what made the results reliable. The direction came from the
person: what the remaster should be, and when an answer was good enough to move on.

## Running the checks yourself

With your own ROM at `roms/adventure.a26`, the emulator core in `cores/` and the environment from the README:

```sh
.venv/bin/python tests/verify_ram.py            # 11 claims about the RAM and the object list
.venv/bin/python tests/verify_rooms.py          # every visible room's walls against the real frames
.venv/bin/python tests/verify_rooms.py --reveal # ...and the dark rooms too, on a patched copy of the ROM
.venv/bin/python tests/verify_exits.py          # walk out of every exit in game 1
.venv/bin/python tests/verify_render.py         # the whole picture rebuilt from RAM, pixel for pixel
.venv/bin/python tools/room_sheet.py            # every room drawn from the decoded data
.venv/bin/python tools/rebuild_2600.py          # the emulator beside the rebuild, live (D shows differences)
```
