# John Henry

Some background on why this exists and how it was made.

I'm not really a big gamer. But the games that stuck with me are a short list: *Adventure* on the Atari 2600,
*The Goonies* on the Commodore 64, and, years later, *Myst*. They have one thing in common: you work the world
out by playing it. Nothing tells you what the key is for or why the bat keeps taking things. You poke at it
until it makes sense.

## First, The Goonies

This isn't the first game I've done this to. Before Adventure Forever came a remaster of *The Goonies*: the
Commodore 64 game, running as it is, redrawn as if it had been made for the Amiga. It worked, and it isn't
released (yet). It was a much bigger job, with Stable Diffusion doing a lot of the drawing, including
backgrounds and detail the original never had.

Underneath, it's the same idea as this project: let the original game run untouched, read what it's doing,
and draw it again.

## Then Adventure, out of order

Adventure came first in my life and second here, and it turned out to be an almost perfect target. The whole
game is 4 KB of ROM and 128 bytes of RAM, and people have been taking it apart and writing it up for decades,
down to a fully commented disassembly. Everything the game knows fits in a table you can read in one sitting.
That's what makes a live remaster possible: if you know where the game keeps the dragons, you can draw the
dragons however you like.

There's also an odd bit of history. Warren Robinett made Adventure after playing *Colossal Cave Adventure*,
the text game, at the Stanford Artificial Intelligence Laboratory, where Don Woods had expanded it. So the
first action-adventure on a home console began as an idea carried out of an AI lab. Forty-odd years later,
this remaster of it was written with an AI.

## Why it's vibe coded

I didn't write this code by hand. I described what I wanted, looked at what came back, played it and said
what was wrong, over and over, with Claude Code doing the typing. I typed very little of it.

The approach was my idea. It's related to the HD packs some emulators support, which swap in better graphics
tile by tile, but it's a different problem: it never touches the 2600's picture. It reads what the game means
from its RAM and draws the scene again. I directed the architecture the way I would at work, as the code
reviewer: what a look, a cast, a world and a pack are, where the boundaries go, and when something needed
refactoring because it stopped making sense to a person reading it. The looks and packs follow one thread,
the games I grew up with and the ones that came after. Adventure and Zelda were solving very similar problems
(a world of rooms, keys, items that change what you can do, monsters in the way), which is why Adventure in an
NES look feels like it could have existed.

It suits a project like this. The game is fixed and thoroughly documented, so the rules are clear (never
change the game, draw everything where the game has it), and the tests prove nothing broke. Inside those
rules, the fun part is ideas: Adventure as a crayon drawing, or as an office floor that goes on too long.
Describing an idea is quicker than drawing it a pixel at a time, and it means anyone with an idea can make
one.

If you want to extend it, I'd suggest working the same way. Open an assistant in the repository, describe the
pack or look you want, and push back until it's right. [CLAUDE.md](CLAUDE.md) gives it the rules, and
`tools/preview.py` lets it see what it made. [Making a pack](docs/making-a-pack.md#start-with-an-ai-assistant)
has an example.

John Henry raced the steam drill and won, once. This time the drill and I were on the same side.
