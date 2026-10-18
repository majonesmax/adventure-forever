# Platform rules

A **look** is the console. It draws the status bar and the title and win screens itself, and shows any
**cast** in any **world** after adapting their pictures to its own rules. Draw a pack once, richly, and
each console reduces it ("author rich, platforms reduce").

## What each look does to the pictures

| | NES (`nes`) | SNES (`snes`) | VGA (`vga`) | Paper (`paper`) | Template (`template`) |
|---|---|---|---|---|---|
| **Colours** (cast, rooms, gates) | snapped to the nearest of the NES palette's colours (`shared/palettes.py`) | 15-bit: 32 levels per channel | VGA's: 256 colours, each from 262,144 (64 levels per channel), picked for the cast and world (`looks/vga/palette.py`); everything the nearest of them, and every screen in those 256 only | a box of 17 crayons: the nearest crayon; near-paper colours are bare paper. Rooms and gates are waxy (the paper's grain shows through) and a room's biggest colour is coloured in lightly | as drawn |
| **Colours per sprite** | not limited (a real NES sprite has 3 + transparent; the classic cast keeps to that) | at most 15 (a SNES sprite palette): more are merged | not limited | not limited | not limited |
| **Sprite outlines** | as drawn | dark edge pixels become a dark shade of the colour beside them: a softer, cartoon-style line | as drawn | as drawn | as drawn |
| **Transparency** | solid or clear (every look: alpha under 128 is clear) | solid or clear | solid or clear | solid or clear | solid or clear |
| **Flashing pixels** (magenta) | the game's flashing colour | the game's flashing colour | the game's flashing colour | the game's flashing colour | the game's flashing colour |
| **Size** | as drawn (after the pack's `scale`) | as drawn | as drawn | as drawn | as drawn |
| Where | `NesLook.adapt` / `adapt_scenery` in `looks/nes/look.py` | `SnesLook.adapt` / `adapt_scenery` in `looks/snes/look.py` | `VgaLook.adapt` / `adapt_scenery` in `looks/vga/look.py` | `PaperLook.adapt` / `adapt_scenery` in `looks/paper/look.py` | `TemplateLook` |

## What each look uses

| | NES | SNES | VGA | Paper | Template |
|---|---|---|---|---|---|
| world: rooms and gates | yes | yes | yes | yes | yes |
| world: the places' names | no: the status bar shows ADVENTURE and the game number | yes, in the status bar, framed in the place's colour | yes, in the status bar | yes, handwritten in the status bar | no |
| world: `title_small`, `footer` | no | yes, on the title screen | yes: the status bar and the title's message box | yes: the status bar and the title's index card | no |
| world: the gold castle's wall tile | yes: the title screen's miniature castle (flat gold without one) | no: the title shows the gold castle room itself | no: the title shows the gold castle room itself | no: the title draws the gold castle room in | no |
| cast: hero, dragons, bat, items, bridge | yes | yes | yes | yes | yes |
| cast: messenger | no: a text banner, then a CONGRATULATIONS screen with the hero holding the chalice | yes, in a speech bubble with `win_lines` | yes, beside `win_lines` in a message box (left out if it doesn't fit) | yes, beside `win_lines` on an index card (left out if it doesn't fit) | no: the first of `win_lines` |
| cast: `title_cast` | no | yes, in front of the castle | no | yes, in the gold castle room | no |
| held item drawn | under the hero, like the original | over the hero (the hero is bigger), except the bridge | under the hero | under the hero | under the hero |

Anything a cast or world leaves out is drawn as the **original 2600 graphic**, so every combination is
playable.

## How true to the real machine is each look?

Each look keeps its platform's **colour rules**. None of them keeps its **hardware limits** - how many sprites
fit on a line, which tiles share a palette - because packs are drawn freely and every look shows every pack.
The rest is the era's style, chosen by eye.

| | What the real machine did | What the look enforces | What is style, not a rule |
|---|---|---|---|
| **NES** | 64 colours (the 2C02's palette); 4 palettes of 3 colours for sprites and 4 for the background, about 25 colours on screen; one background palette per 16×16 square; 8×8 tiles; 8 sprites a line; 256×240 | the 64 colours, and the 256×240 screen | 3 colours a sprite is a habit of the classic cast, not a rule; the palette, tile and sprite-count limits aren't enforced |
| **SNES** | 32,768 colours (15-bit); 256 on screen; sprites of 15 colours + clear, from 8 palettes; 32 sprites a line; usually 256×224 | 15-bit colour and 15 colours a sprite | the soft outlines; the screen is 256×240; the 256-on-screen and palette-count limits aren't enforced |
| **VGA** (mode 13h) | 256 colours on screen, each from 262,144 (64 levels a channel), chosen by the game - often anew for each scene; 320×200, stretched to a 4:3 monitor so pixels were a little taller than wide | 64 levels a channel; 256 colours on screen, picked for the cast and world by median cut (the era's paint tools did the same), 16 of them the card's standard colours for menus and text; every screen in those 256 only | one palette for the whole world, not one per room; the 256×240 screen with square pixels (every look shares the game's room layout); the menu strip, message boxes and DOS prompt |
| **Paper** | no machine: crayons on paper | a box of 17 crayons | all of it |

## The same in every look

These come from the game itself and no look changes them (see [ARCHITECTURE.md](ARCHITECTURE.md)):

- **Positions.** Everything is drawn where the game has it. Hits, pickups and walls are decided by the game's
  own small shapes, so a big villain only "counts" in its middle.
- **Walls.** Where the walls are is the game's; a world only chooses what they're made of.
- **Dark rooms.** The catacombs and the black maze are lit only by a torch around the hero. (Away from
  it, a look decides what dark is: black in most, blank paper in the paper look - `unlit`.)
- **The screen.** 256x240, the room 240x192 under a 48-pixel status bar (`shared/layout.py`). A look with a
  different layout implements `Look` from `looks/base.py` directly.
- **Timing.** One picture per game frame, 60 a second.
