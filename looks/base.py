"""What a LOOK is: the contract every way of drawing the game implements, and shared machinery for looks
that use the "whole room" layout.

The game runs unmodified in the emulator. Every frame the app hands a look a GameState (engine/state.py:
which room, where the hero and every object are, what he carries, whether the game is won) and the look
returns a picture. A look never changes the game - it only draws it.

A look is a PLATFORM - the console: how the game is drawn - the screen layout, the colour rules, the status
bar, the title and win screens. What's drawn comes from content/: a CAST (who: hero, dragons, bat, items) and
a WORLD (where: each place's walls, floor and gates, and their names). Any look shows any cast in any world,
adapting their pictures to its own rules.

    Look         the contract - what the app needs from any look (draw a screen; say where the room and
                 the hero are, so room-to-room scrolls can slide them). Implement it directly for a look
                 with its own layout.
    RoomLook     a Look with the whole-room layout (shared/layout.py) and everything about placing things
                 already done: the world's rooms, the cast at the game's positions, the hero's walk cycle,
                 the held item, dark rooms lit by a torch, the win sequence, the original 2600 graphic for
                 anything the cast or world leaves out. A subclass supplies its rules and screens - see the
                 methods marked PLATFORM below.

The built-in looks are RoomLooks: looks/nes (NesLook) and looks/snes (SnesLook). The smallest complete
example is looks/template_look.py - copy it to start a new look.
"""

from abc import ABC, abstractmethod

import numpy as np

from engine import objects as O
from engine import palette as P
from shared import layout as L
from content.pictures import FLASH
from content.world import CASTLES
from shared import palettes as PAL
from shared.pixelart import blit

DRAGON_COLOUR = {0x06: "red", 0x07: "yellow", 0x08: "green"}  # object number -> which dragon
AUTHOR = 0x04  # Warren Robinett's credit: always shown in the 2600's own colours, never a remaster's
BRIDGE, BAT = 0x0A, 0x0E


class Look(ABC):
    """THE LOOK CONTRACT. The app (play.py and app/) uses a look only through these.

    platform   the look's short id: `play.py --look <platform>`, recordings' file names ("nes", "snes")
    key        this look with its cast and world: the platform, "+<cast>" if the cast isn't the look's own,
               "@<world>" if the world isn't ("snes+classic", "nes@pbj", "snes+classic@classic")
    name       label shown over the look's pane in the grid view ("SNES REMASTER")
    ROOM_RECT  (x, y, w, h) of the room on the screen - a room-to-room scroll slides only this area
    """

    platform = key = "?"
    name = "?"
    SCREEN_W, SCREEN_H = L.SCREEN_W, L.SCREEN_H  # every look draws a 256x240 screen
    ROOM_RECT = L.ROOM_RECT

    @abstractmethod
    def draw(self, st, frame_no, actors=True):
        """The screen for this frame: an (SCREEN_H, SCREEN_W, 3) uint8 RGB array.

        st        the GameState (engine/state.py)
        frame_no  counts up once per game frame - use it for anything that animates or flashes
        actors    False = leave out the hero and the item he holds (a room scroll draws those itself, once,
                  sliding across the seam between the two rooms)
        Called every frame, in order - a look may keep state between calls (e.g. which way the hero faces)."""

    @abstractmethod
    def actors(self, st, frame_no):
        """What a room scroll carries across: {"hero": (sprite, x, y)} plus "item" when one is held, in the
        order to draw them. Sprites are RGBA arrays; x, y are pixels inside ROOM_RECT."""

    def won(self, st):
        """Is the game won? (The music switches to the win tune.) The game's own flag - rarely worth changing."""
        return st.won


class HeroAnim:
    """Which way the hero faces and his walk cycle, worked out from how his position changes (the 2600 hero
    is just a square). Any sideways movement -> side view ("left"/"right"); pure up/down -> back/front view
    ("up"/"down"). frame() is 0 standing, alternating 0/1 while walking."""

    def __init__(self):
        self.prev, self.view, self.moving_for, self.still_for = None, "down", 0, 0

    def update(self, st):
        pos = (st.room_num, *st.hero)
        if self.prev and pos[0] == self.prev[0]:
            dx, dy = pos[1] - self.prev[1], pos[2] - self.prev[2]
            if dx:
                self.view = "left" if dx < 0 else "right"
            elif dy:
                self.view = "up" if dy > 0 else "down"  # the game's y counts up the screen
            if dx or dy:
                self.moving_for, self.still_for = self.moving_for + 1, 0
            else:
                self.still_for += 1
                if self.still_for > 4:  # the game moves the hero on 2 of every 3 frames - don't stutter
                    self.moving_for = 0
        self.prev = pos

    def frame(self):
        return (self.moving_for // 8) % 2 if self.moving_for else 0


def dragon_pose(state):
    """A dragon's state byte -> its pose: "dead" (1), "normal" (0, or 2 = it has eaten the hero), "roar"
    (anything higher: attacking, jaws open). From the game's MoveDragon routine."""
    return "dead" if state == 1 else "normal" if state in (0, 2) else "roar"


def original_graphic(obj, state, nes_colour=None, col_w=L.COL_W):
    """An object's own 2600 graphic as an RGBA sprite: each bit col_w/4 * its width px wide, each row 2 px
    tall, in one NES colour, with a 1 px black outline."""
    g = O.graphic_for_state(obj, state)
    bw = max(1, int(round(col_w / 4 * obj["width"])))
    w, hh = 8 * bw + 2, 2 * len(g) + 2
    mask = np.zeros((hh, w), bool)
    for i, byte in enumerate(g):
        for b in range(8):
            if (byte >> (7 - b)) & 1:
                mask[1 + 2 * i:3 + 2 * i, 1 + b * bw:1 + (b + 1) * bw] = True
    outline = (np.roll(mask, 1, 0) | np.roll(mask, -1, 0) | np.roll(mask, 1, 1) | np.roll(mask, -1, 1)) & ~mask
    im = np.zeros((hh, w, 4), np.uint8)
    colour = nes_colour if nes_colour is not None else PAL.ORIGINAL_TO_NES.get(obj["colour"] & 0xFE, 0x30)
    im[mask] = (*PAL.NES[colour], 255)
    im[outline] = (*PAL.NES[PAL.BLACK], 255)
    return im


class RoomLook(Look):
    """A look in the whole-room layout (shared/layout.py), showing a cast in a world. Supplies draw() and
    actors(); a subclass supplies its platform through the methods marked PLATFORM.

    platform       the look's key (`--look`)
    platform_name  its label in the grid view
    own_pack       the pack whose cast and world it shows unless others are chosen (--cast / --world, C / W)
    SPLASH_AFTER   frames of win_banner over the room before win_splash takes over (if it returns a screen)
    """

    platform = platform_name = "?"
    own_pack = "classic"
    SPLASH_AFTER = 90

    scenery = {}  # (platform, world, room number) -> the room as this platform shows it: shared, never changes

    def __init__(self, reader, cast, world):
        """reader: the ROM's object table (Game().reader) - which graphic and size each object has.
        cast, world: content/cast.py, content/world.py - the cast's pictures go through adapt() once, here."""
        self.reader = reader
        self.cast, self.world = cast, world
        self.key = (self.platform + ("" if cast.key == self.own_pack else f"+{cast.key}")
                    + ("" if world.key == self.own_pack else f"@{world.key}"))
        self.name = " - ".join([self.platform_name] + [part.name for part in (cast, world)
                                                       if part.key != self.own_pack])
        self.anim = HeroAnim()
        self.sprite_cache = {}
        self.cur_st = None
        self.won_at = None
        self.pal_2600, self.nearest = P.load(), {}
        yy, xx = np.mgrid[0:L.ROOM_H, 0:L.ROOM_W]
        self.grid_yx = (yy, xx)
        self.hero = {view: [self.adapt(f) for f in frames] for view, frames in cast.hero().items()}
        self.dragons = {k: self.adapt(v) for k, v in cast.villains().items()}
        self.bat = {k: self.adapt(v) for k, v in cast.bat().items()}
        self.items = cast.items()  # adapted when drawn: a flashing item changes colour every few frames
        self.flashes = {n for n, art in self.items.items() if np.all(art[..., :3] == FLASH, axis=2).any()}

    # ---- PLATFORM: what a subclass supplies --------------------------------------------------------------

    def adapt(self, sprite):
        """The platform's rules for a cast's picture (an RGBA array) -> the picture as this look shows it:
        e.g. snapped to the NES's colours. Called once per picture (and per flash colour). Default: as is."""
        return sprite

    def adapt_scenery(self, picture):
        """The platform's rules for the world's pictures - rooms (RGB) and gates (RGBA). Called once per room
        and gate size. Default: as is."""
        return picture

    def object_sprite(self, n, state, box_w, box_h, frame_no):
        """Any object other than the hero and dragons (objects.py numbers them: 09 sword, 0A bridge, 0B-0D
        keys, 0E bat, 10 chalice, 11 magnet, 01-03 castle gates...). box_w, box_h: the original's size in
        room pixels - the bridge and gates should fill it. RGBA, drawn centred on the original's box.
        This one gives the cast's (and the world's gates); a look can add stand-ins by overriding it and
        asking super() first. None = draw the original graphic."""
        if n == BAT:  # wings up or down: the same rule as the ROM's bat states
            return self.bat.get("up" if state <= 3 else "down")
        if n == BRIDGE:
            return self.bridge_sprite(int(box_h), int(round(box_w)))
        if n in CASTLES:  # a castle's gate, at its current height
            w, h = int(round(box_w)), int(box_h)
            key = ("gate", n, w, h)
            if key not in self.sprite_cache:
                gate = self.world.gate(CASTLES[n], w, h) if h > 0 else None
                self.sprite_cache[key] = None if gate is None else self.adapt_scenery(gate)
            return self.sprite_cache[key]
        if n in self.items:
            art = self.items[n]
            flash = None
            if n in self.flashes:  # this frame's flashing colour
                flash = self.obj_colour(n, frame_no)
                flash = PAL.flash_colour(frame_no) if flash is None else flash
            key = ("item", n, flash)
            if key not in self.sprite_cache:
                self.sprite_cache[key] = self.adapt(art if flash is None else self.flashing(art, flash))
            return self.sprite_cache[key]
        return None

    def bridge_sprite(self, h, w=None):
        """The bridge, h pixels long (centred in w if given): the cast's, adapted; None = the original."""
        key = ("bridge", h, w)
        if key not in self.sprite_cache:
            bridge = self.cast.bridge(h, w)
            self.sprite_cache[key] = None if bridge is None else self.adapt(bridge)
        return self.sprite_cache[key]

    @abstractmethod
    def draw_hud(self, screen, st, frame_no):
        """The status bar: everything above ROOM_RECT on `screen` (paint it in place)."""

    @abstractmethod
    def title_screen(self, st, frame_no):
        """The whole screen for the game-select room (st.on_title_screen). Return a new RGB array."""

    @abstractmethod
    def win_banner(self, screen, st, frame_no):
        """Painted over the room when the game is won (st.won)."""

    def win_splash(self, st, frame_no):
        """A full-screen victory picture, shown SPLASH_AFTER frames after the win; None = keep the banner."""
        return None

    def carried_on_top(self, n):
        """Draw the held item over the hero (True) or under him, like the original (False)?"""
        return False

    # ---- shared machinery ---------------------------------------------------------------------------------

    def room_image(self, room, light=1.0):
        """The room's walls and floor as this look shows them: the world's picture through adapt_scenery -
        dimmed to `light` first when the world's lights dip (world.lighting)."""
        light = round(light, 2)
        key = (self.platform, self.world.key, room["room"], light)
        if key not in self.scenery:
            picture = self.world.room(room)
            if light < 1.0:
                picture = (picture.astype(float) * light).astype(np.uint8)
            self.scenery[key] = self.adapt_scenery(picture)
        return self.scenery[key]

    def hero_sprite(self, view, frame):
        """The hero: view is "down" / "up" / "left" / "right", frame 0 (standing) or 1 (stride). RGBA."""
        return self.hero[view][frame]

    def dragon_sprite(self, pose, colour):
        """A dragon: pose "normal" / "roar" / "dead", colour "red" / "yellow" / "green". RGBA, drawn centred
        on the original dragon with its feet on the bottom of the original's box. None = draw the original."""
        return self.dragons.get((pose, colour))

    @staticmethod
    def flashing(sprite, colour):
        """The sprite with its FLASH pixels (content/pictures.py) in NES colour `colour`."""
        mark = np.all(sprite[..., :3] == FLASH, axis=2) & (sprite[..., 3] > 0)
        if not mark.any():
            return sprite
        out = sprite.copy()
        out[mark, :3] = PAL.NES[colour]
        return out

    def held_icon(self, n, frame_no):
        """The carried object as the status bar's item box shows it."""
        spr = self.bridge_sprite(24) if n == BRIDGE else self.object_sprite(n, 0, 12, 12, frame_no)
        return spr if spr is not None else self.original_sprite(n, 0, frame_no)

    def obj_colour(self, n, frame_no):
        """The NES colour for a flashing object (odd 2600 colour) this frame, else None."""
        c = self.reader.objects[n]["colour"]
        if not c & 1:
            return None
        if n == AUTHOR and self.cur_st is not None:  # exactly what the 2600 shows this frame (ChangeColor)
            rgb = tuple(self.pal_2600[self.cur_st.colour(c) & 0xFE])
            if rgb not in self.nearest:
                self.nearest[rgb] = PAL.nearest_nes(rgb)
            return self.nearest[rgb]
        return PAL.flash_colour(frame_no)

    def original_sprite(self, n, state, frame_no):
        """Object n's own 2600 graphic (cached) - for anything the art methods don't draw."""
        colour = self.obj_colour(n, frame_no)
        key = (n, state, colour)
        if key not in self.sprite_cache:
            self.sprite_cache[key] = original_graphic(self.reader.objects[n], state, nes_colour=colour)
        return self.sprite_cache[key]

    def placed(self, n, x, y, s, frame_no):
        """Object n at the game's position (x, y) in state s -> (sprite, room-space x, y) to blit."""
        obj = self.reader.objects[n]
        ox, oy = L.to_room(x - 1 + (1 if obj["width"] > 1 else 0), 224 - 2 * y)
        if n in DRAGON_COLOUR:
            spr = self.dragon_sprite(dragon_pose(s), DRAGON_COLOUR[n])
            if spr is not None:  # centred on the original 8-pixel-wide graphic, feet on the bottom of its box
                g_h = 2 * len(O.graphic_for_state(obj, s))
                return spr, ox + 6 - spr.shape[1] / 2, oy + g_h - spr.shape[0]
        box_w, box_h = 8 * obj["width"] * L.COL_W / 4, 2 * len(O.graphic_for_state(obj, s))
        spr = self.object_sprite(n, s, box_w, box_h, frame_no)
        if spr is not None:  # centred on the original's box
            return spr, ox + (box_w - spr.shape[1]) / 2, oy + (box_h - spr.shape[0]) / 2
        return self.original_sprite(n, s, frame_no), ox - 1, oy - 1

    def hero_placed(self, st):
        """(sprite, x, y): feet on the bottom of the game's hit-box. Overlap with a wall then only happens
        upward - the head against the wall above, which reads as standing in front of it."""
        hx, hy = L.to_room(st.hero[0], 224 - 2 * st.hero[1] + 4)  # hit-box centre
        spr = self.hero_sprite(self.anim.view, self.anim.frame())
        return spr, hx - spr.shape[1] / 2, hy + 4 - (spr.shape[0] - 1 - self.cast.foot_gap)

    def carried_placed(self, st, n, x, y, s, frame_no):
        """Where the held item is drawn: exactly where the game has it - moving it would make hits miss
        where they looked like they landed (the game hit-tests its own positions)."""
        return self.placed(n, x, y, s, frame_no)

    def actors(self, st, frame_no):
        out = {}
        for n, x, y, s in st.objects:
            if n == st.carried:
                out["item"] = self.carried_placed(st, n, x, y, s, frame_no)
        if "item" in out and self.carried_on_top(st.carried):
            return {"hero": self.hero_placed(st), **out}
        out["hero"] = self.hero_placed(st)
        return out

    def draw(self, st, frame_no, actors=True):
        self.anim.update(st)
        self.cur_st = st
        if st.on_title_screen:
            return self.title_screen(st, frame_no)
        room = self.room_image(st.room, self.world.lighting(st.room_num, frame_no)).copy()
        hx, hy = L.to_room(st.hero[0], 224 - 2 * st.hero[1] + 4)  # hero hit-box centre
        for n, x, y, s in sorted(st.objects, key=lambda o: -o[0]):
            if n == 0:  # the "surround" (the lit square in dark rooms): replaced by the torch light below
                continue
            if n == st.carried:
                if actors and not self.carried_on_top(n):
                    blit(room, *self.carried_placed(st, n, x, y, s, frame_no))
                continue
            blit(room, *self.placed(n, x, y, s, frame_no))
        if actors:
            blit(room, *self.hero_placed(st))
            for n, x, y, s in st.objects:
                if n == st.carried and self.carried_on_top(n):
                    blit(room, *self.carried_placed(st, n, x, y, s, frame_no))
        if st.room["colour"] == 0x08:  # a dark room: only a banded torch light around the hero shows it
            yy, xx = self.grid_yx
            d = np.hypot(xx - hx, (yy - hy) * 0.9)
            light = np.round(np.clip(1.35 - d / 34.0, 0, 1) * 3) / 3
            room = (room * light[..., None]).astype(np.uint8)
        screen = np.zeros((L.SCREEN_H, L.SCREEN_W, 3), np.uint8)
        x0, y0, w, h = self.ROOM_RECT
        screen[y0:y0 + h, x0:x0 + w] = room
        self.draw_hud(screen, st, frame_no)
        if self.won(st):
            if self.won_at is None:
                self.won_at = frame_no
            if frame_no - self.won_at >= self.SPLASH_AFTER:
                splash = self.win_splash(st, frame_no)
                if splash is not None:
                    return splash
            self.win_banner(screen, st, frame_no)
        else:
            self.won_at = None
        return screen
