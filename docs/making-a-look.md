# Making a look

A **look** is the console: a complete way of drawing Adventure. It owns the rules (what colours a picture
may have, how outlines are drawn), the status bar, and the title and win screens. NES and SNES are looks. An
Amiga look, a C64 look, a Game Boy look would each be one more.

What it draws comes from packs ([making a pack](making-a-pack.md)): a **world** (each place's walls, floor and
gates, and their names) and a **cast** (the hero, dragons, items...). Every look shows every cast in every
world; your look only says how their pictures are adapted to its rules.

An AI coding assistant can build one with you: [CLAUDE.md](../CLAUDE.md) has the rules, and
`tools/preview.py --look <yours>` shows it every look's key moments in one picture.

The game itself never changes. Every frame, your look is handed a `GameState` (where everything is) and
returns a 256x240 picture.

## The quick way: start from the template

```sh
cp looks/template_look.py looks/my_look.py
python play.py --look template                          # with its own cast and world
python play.py --look template --cast pbj --world pbj   # ... and with others
```

The template is about 60 lines. It's a `RoomLook`, which means the hard part is already done: the world's
rooms are drawn, the cast is placed where the game has it, the hero walks and faces the right way, the held
item follows him, dark rooms are lit by a torch, and the win sequence plays. Your look supplies the console:

| Method / attribute | What | Required |
|---|---|---|
| `platform`, `platform_name` | its key (`--look`, recordings) and its label in the grid view | yes |
| `own_pack` | the pack whose cast and world it shows unless others are chosen | yes |
| `adapt(sprite)` | the console's rules for a cast picture (RGBA in, RGBA out), called once per picture | no (as drawn) |
| `adapt_scenery(picture)` | the same for the world's rooms (RGB) and gates (RGBA) | no (as drawn) |
| `draw_hud(screen, st, frame_no)` | paints the status bar above the room | yes |
| `title_screen(st, frame_no)` | the whole game-select screen | yes |
| `win_banner(screen, st, frame_no)` | paints over the room once the chalice is home | yes |
| `win_splash(st, frame_no)` | a full-screen victory picture shown a moment later, or None | no |
| `object_sprite(n, state, box_w, box_h, frame_no)` | stand-ins for what a cast leaves out: ask `super()` first, it returns the cast's (and the world's gates) | no |
| `unlit(room, light)` | what a dark room looks like away from the torch (default: fading to black) | no |
| `carried_on_top(n)` | draw the held item over the hero rather than under | no |

Whatever the cast or world leaves out is the **original 2600 graphic**, so the game is always playable.

`self.cast` and `self.world` are what's being shown. Their words (`self.cast.win_lines`,
`self.world.area_name(room)`, `self.world.title_small`...), colours (`self.world.colour(room)`) and pictures
(`self.cast.picture("messenger")`) are yours to use or ignore. Put what yours does in
[platform rules](platform-rules.md).

## Make it part of the game

Add it to `LOOKS` in `looks/__init__.py`, and L will cycle through it:

```python
LOOKS = {"nes": NesLook, "snes": SnesLook, "mylook": MyLook}
```

## What you get in a GameState

`st.room_num`, `st.room` (walls, colour, exits), `st.hero` (x, y), `st.carried`, `st.objects` (every object
in the room: number, x, y, state), `st.game` (1–3), `st.won`, `st.eaten_by`, `st.on_title_screen`.
See `engine/state.py`. A look never needs a RAM address.

## Helpers

- `shared/layout.py`: the screen layout, `wall_mask(room)` (where the walls are), `to_room()` (game
  coordinates to pixels).
- `shared/pixelart.py`: draw sprites as text art (`from_ascii`), mirror and edit them, paste them (`blit`).
- `shared/hud.py`: the pixel font (`draw_text`) and box frames for status bars.
- `shared/palettes.py`: the NES palette, if your look wants authentic 8-bit colours.

## A different layout

`RoomLook` assumes the whole room on one screen under a status bar (`shared/layout.py`). For something else
(a scrolling camera, a widescreen room, a split screen) implement `Look` from `looks/base.py` directly. It
asks for just three things: `draw(st, frame_no, actors)`, `actors(st, frame_no)` (where the hero and
his item are, so room scrolls can carry them), and `ROOM_RECT` (which part of the screen is the room).

## Check it

`tests/golden.py` renders 20 game moments in every look with every cast in every world, including yours once it's in
`looks/__init__.py`. Run it with `--update` to record your look's pictures, then without, after any change,
to prove nothing else moved. If a moment changes, the picture is saved in `shots/golden_fail/` so you can
see what happened.
