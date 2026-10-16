# Packs

A pack is a folder that brings a **cast** (who's in the game: the hero, the dragons, the bat, the items, the
bridge, who announces the win), a **world** (where: each place's walls, floor and gates, and their names),
or both. Every look (NES, SNES) shows every cast in every world, adapting the pictures to its own rules.

| Pack | Cast | World |
|---|---|---|
| `classic/` | the knight, the dragons, the bat, the items (the NES look's own) | brick and stone castles |
| `pbj/` | PBJ, Alice the Scottie, the Yeti, the hen, the Bog, the magpie, the Storybook (the SNES look's own) | the candy, ice and fire kingdoms |
| `template/` | a hero and one dragon | one wall tile, one floor tile |

Inside each: `pack.json`, `cast/` (pictures), `world/` (tiles), and optionally `source/`, the text art the
pictures were drawn from and the script that writes them. A pack doesn't need `source/`; any pixel-art
editor will do.

**Your own packs** go in `private/packs/` (git-ignored, so they're never published), or here if they're for
everyone. Either way they're found by themselves:

```sh
cp -r packs/template private/packs/mine
.venv/bin/python play.py --pack mine        # in the game: C cycles the casts, W the worlds
```

The guide: [docs/making-a-pack.md](../docs/making-a-pack.md). Every picture name and pack.json field:
`content/cast.py` and `content/world.py`.
