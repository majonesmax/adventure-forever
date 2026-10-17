# Making a pack

Adventure Forever separates three things:

| | What it is | Examples | Chosen with |
|---|---|---|---|
| **look** | the console: how everything is drawn (colour rules, status bar, title and win screens) | NES, SNES, VGA | `--look`, **L** |
| **cast** | who's in the game: the hero, the dragons, the bat, the items, the bridge, who announces the win | the knight; PBJ and friends | `--cast`, **C** |
| **world** | where it happens: each place's walls, floor and castle gates, the places' names, the title's word | the brick castles; the candy, ice and fire kingdoms | `--world`, **W** |

A **pack** is a folder that brings a cast, a world, or both. It's what you make, copy and share. Any look
shows any cast in any world: PBJ in the brick castles on an NES, or the knight in the candy kingdom on a
SNES. Each look adapts the pictures to its own rules ([platform rules](platform-rules.md)), so draw them once,
as richly as you like.

| Pack | Cast | World | Own pack of |
|---|---|---|---|
| `packs/classic` | the knight, three dragons, the bat, the items, a wooden bridge | brick and stone castles, hedges, catacombs | the NES look |
| `packs/pbj` | PBJ in her bear-ear hat, Alice the Scottie (the bridge, and the messenger), the Yeti, a giant hen, the Bog, a magpie, the Storybook | the sweet kingdoms: candy, ice and fire castles, a dark forest, crypts, crystal caves | the SNES look |
| `packs/template` | a hero and one dragon | one wall tile and one floor tile | the template look |

```sh
python play.py --list                                # every look and pack there is
python play.py --look nes --cast pbj                  # PBJ on the NES, in the NES look's own world
python play.py --look snes --cast classic --world classic
python play.py --pack mine                            # a pack's cast in its own world
```

Until you choose (with an option, or C or W in the game), each look shows its own pack's cast and world.

## The quick way: start from the template

```sh
cp -r packs/template private/packs/mine
python play.py --pack mine
```

The folder is found by itself. **`private/` is git-ignored**, so a personal pack (your family as the
heroes, fan art of a show you love) never gets published by accident. A pack meant for everyone goes in
`packs/`. Now replace the pictures; any pixel-art editor works (Aseprite, Piskel, LibreSprite...).

```
private/packs/mine/
    pack.json         names and settings, for the cast and the world
    cast/             the cast's pictures
    world/            the world's tiles
    source/           optional: whatever you made the pictures from
```

A pack with only `cast/` is just a cast (pick a world for it with W); one with only `world/` is just a world.

## The cast

Only `cast/hero_down_0.png` is required. Leave anything else out and the original 2600 graphic is drawn.

| Picture | What | If it's missing |
|---|---|---|
| `hero_down_0.png`, `hero_down_1.png` | front view: standing, mid-stride | (required) / the standing picture |
| `hero_up_0.png`, `hero_up_1.png` | back view | the front view |
| `hero_right_0.png`, `hero_right_1.png` | side view, facing right | the front view |
| `hero_left_0.png`, `hero_left_1.png` | facing left | the side view, mirrored |
| `dragon_normal_red.png` ... | pose `normal` / `roar` (attacking) / `dead`, colour `red` / `yellow` / `green` | `dragon_<pose>.png`, one design for all three |
| `dragon_dead_<colour>.png` | defeated | the normal pose upside down (what the 2600 does) |
| `bat_up.png`, `bat_down.png` | the thief, flapping | down: the up picture |
| `item_sword.png`, `item_magnet.png`, `item_chalice.png` | the items | |
| `item_key_gold.png`, `item_key_white.png`, `item_key_black.png` | the three castle keys | |
| `bridge_top.png`, `bridge_middle.png`, `bridge_bottom.png` | the bridge, stretched to the length the game needs: the top, the middle repeated, the bottom | |
| `messenger.png`, or `messenger_0.png`, `messenger_1.png`... | who announces the win (several frames take turns) | |
| anything else | e.g. a picture just for the title screen (see `title_cast`) | |

**Sizes** that sit well in the 240x192 rooms: hero about 16x26, dragons about 26x36, items about 16x8.
Bigger is fine: if you draw at double size (or more), say so with `scale` and the looks shrink the pictures.
**Transparency**: pixels are solid or clear. **Flashing**: pixels of exactly magenta `(255, 0, 255)` flash
through the game's colours, as the chalice does in the original.

## The world

The game decides where the walls are; the world decides what they're made of. Worlds use the game's own
places, so every world fits every room:

| Place | Rooms | | Place | Rooms |
|---|---|---|---|---|
| `meadow` | the green rooms outside | | `black_castle` | outside the black castle |
| `gold_castle` | outside the gold castle | | `black_castle_inside` | inside it |
| `gold_castle_inside` | inside it | | `black_maze` | the dark maze beyond it |
| `labyrinth` | the blue maze | | `red_maze` | the red maze |
| `catacombs` | the dark maze near the gold castle | | `purple_room` | the purple room |
| `white_castle` | outside the white castle | | `credit_room` | a purple room with a secret |
| `white_castle_inside` | inside it | | | |

A world's pictures are **tiles**, repeated across the room (one that repeats seamlessly looks best):

| Picture | What |
|---|---|
| `wall_<place>.png`, `floor_<place>.png` | one place's walls and floor |
| `wall.png`, `floor.png` | every place without its own |
| `gate_<castle>.png`, `gate.png` | a castle's gate (`gold`, `white`, `black`): its bottom part shows as the gate rises |

Without a wall tile the walls are the game's own colour for that room; without a floor tile the floor is
grey; without a gate, the original gate. Tiles can also be named anything and given to places in
`pack.json` (below), so one tile can serve several places.

## pack.json

Every field is optional; `{}` is a valid pack.json.

```json
{
  "name": "MY PACK",
  "cast": {
    "name": "THE HEROES",
    "win_lines": ["YOU WIN!", "THE CHALICE", "IS HOME!"],
    "title_cast": ["hero_down_0", "messenger"],
    "foot_gap": 1
  },
  "world": {
    "name": "THE MOUNTAINS",
    "title_small": "FOREVER",
    "outline": [0, 0, 0],
    "shadow": 0.6,
    "areas": {
      "default":  {"wall": "rock", "floor": "snow"},
      "red_maze": {"wall": "lava_rock", "name": "THE VOLCANO", "colour": [248, 96, 32]}
    }
  }
}
```

| Cast field | What |
|---|---|
| `name` | shown by `--list` and over the pane in the grid view |
| `win_lines` | three short lines (up to 18 characters each) for the win |
| `title_cast` | which pictures stand in front of the castle on the SNES title screen |
| `messenger_every` | frames each messenger picture shows before the next |
| `foot_gap` | empty rows under the hero's feet in the hero pictures (the feet stand on the bottom of the game's hit-box) |
| `scale` | the pictures are drawn this many times bigger than the room's pixels |

| World field | What |
|---|---|
| `name` | shown by `--list` and in the grid view |
| `title_small` | the small word after ADVENTURE on the SNES title screen and status bar |
| `footer` | the last line of the SNES title screen |
| `outline` | a line around the walls, `[r, g, b]` |
| `shadow` | how dark the walls' shadow on the floor is (0-1) |
| `areas` | per place (or `default`): its `wall` and `floor` tiles (picture names), its `name` in the status bar, its `colour` for screens to frame it with |
| `extends` | another pack's world to start from: its scenery, with your names (e.g. `"extends": "pbj"` and your own `areas` names) |
| `scale` | the tiles are drawn this many times bigger than the room's pixels |

## When pictures aren't enough

A world with rounded walls and scattered flowers, a bridge that fits its box exactly: add Python next to
the pictures.

- `cast/cast.py` with a `CustomCast` class (see `content/cast.py`): the classic cast builds its wooden bridge this way.
- `world/world.py` with a `CustomWorld` class (see `content/world.py`): the pbj world paints its rooms
  (`room()`), its gates and colours this way, and the classic world draws its iron portcullis.

```python
from content.world import World

class CustomWorld(World):
    def room(self, room):
        """The room's walls and floor: a 240x192 RGB picture. shared.layout.wall_mask(room) says where the
        walls are."""
        ...
```

## Drawing sprites as text (optional)

The built-in packs were drawn as text, which is easy to read, edit and compare. Each keeps its text art in
`source/`, with a script that writes the pictures:

```python
from shared.pixelart import from_ascii

HERO = """
...KKKK...
..KSSSSK..
..KSKSKK..
"""
sprite = from_ascii(HERO, {"K": (24, 24, 40), "S": (232, 184, 136)})   # "." is transparent
```

`mirrored(left_half)` builds a symmetric sprite from its left half, and `edited(art, {row: [(col, "text")]})`
makes a variant (an attacking pose is the normal pose with the mouth redrawn). `content.pictures.save_folder`
writes them out. `packs/template/source/template_sprites.py` is the smallest example.

## Sharing a pack

Put the pack folder online - a GitHub repository is easiest (one repository can hold several packs, like
[shall-we-play-a-game](https://github.com/majonesmax/shall-we-play-a-game)). People using the app add it by
downloading it (on GitHub: **Code → Download ZIP**) and **dropping the zip or folder onto the game window**: the
game finds every folder with a `pack.json` inside, copies them into its packs folder, and switches to the
first. People running from source can point at a checkout instead: `ADVENTURE_PACKS=path/to/repo/packs`.

A `cast.py` or `world.py` is code that runs on the player's computer, so say in your README what it does, and
keep packs to pictures and `pack.json` where you can.

## Tips

- Give sprites a dark outline. The SNES look turns each outline pixel into a dark shade of the colour beside
  it, so a black line comes out as a softer edge, and the NES look keeps it crisp.
- Hits are decided by the game's original (small) shapes, so very wide villains look hittable at their
  edges where the game doesn't count a hit. Keep a villain's middle where the action is.
- Try your pack everywhere: `play.py --pack mine`, then L, C and W. The golden test (`tests/golden.py`)
  renders every look with every cast in every world, yours included.
