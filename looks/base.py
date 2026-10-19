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
from typing import Any

import numpy as np

from engine import objects as O
from engine import palette as P
from engine.state import GameState
from shared import layout as L
from content.cast import Cast
from content.pictures import FLASH
from content.world import CASTLES, Room, World
from shared import palettes as PAL
from shared.pixelart import blit
from shared.types import Floats, Picture, Rgb

Placed = tuple[Picture, float, float]   # a sprite and where its top-left goes, in room pixels (x, y)

DRAGON_COLOUR = {0x06: "red", 0x07: "yellow", 0x08: "green"}  # object number -> which dragon
AUTHOR = 0x04  # Warren Robinett's credit: always shown in the 2600's own colours, never a remaster's
BRIDGE, BAT = 0x0A, 0x0E
SURROUND = 0x00  # the lit square around the hero in dark rooms (replaced by the torch light)
DARK_ROOM_COLOUR = 0x08
BOTTOM_LINE = 224  # the TV scan line at a room's bottom: the game's y counts up from there, 2 lines a step
HERO_HALF_HEIGHT = 4  # scan lines from the hero's position to the middle of his hit-box


def scan_line(game_y: int) -> int:
    """The game's y (counting up from the room's bottom) -> the TV scan line that layout.to_room() expects."""
    return BOTTOM_LINE - 2 * game_y


class Look(ABC):
    """THE LOOK CONTRACT. The app (play.py and app/) uses a look only through these.

    platform   the look's short id: `play.py --look <platform>`, recordings' file names ("nes", "snes")
    key        this look with its cast and world: the platform, "+<cast>" if the cast isn't the look's own,
               "@<world>" if the world isn't ("snes+classic", "nes@pbj", "snes+classic@classic")
    name       label shown over the look's pane in the grid view ("SNES REMASTER")
    ROOM_RECT  (x, y, w, h) of the room on the screen - a room-to-room scroll slides only this area
    """

    platform: str = "?"
    key: str = "?"
    name: str = "?"
    SCREEN_W, SCREEN_H = L.SCREEN_W, L.SCREEN_H  # every look draws a 256x240 screen
    ROOM_RECT: tuple[int, int, int, int] = L.ROOM_RECT

    @abstractmethod
    def draw(self, state: GameState, frame_no: int, actors: bool = True) -> Picture:
        """The screen for this frame: an (SCREEN_H, SCREEN_W, 3) uint8 RGB array.

        state     the GameState (engine/state.py)
        frame_no  counts up once per game frame - use it for anything that animates or flashes
        actors    False = leave out the hero and the item he holds (a room scroll draws those itself, once,
                  sliding across the seam between the two rooms)
        Called every frame, in order - a look may keep state between calls (e.g. which way the hero faces)."""

    @abstractmethod
    def actors(self, state: GameState, frame_no: int) -> dict[str, Placed]:
        """What a room scroll carries across: {"hero": (sprite, x, y)} plus "item" when one is held, in the
        order to draw them. Sprites are RGBA arrays; x, y are pixels inside ROOM_RECT."""

    def won(self, state: GameState) -> bool:
        """Is the game won? (The music switches to the win tune.) The game's own flag - rarely worth
        changing."""
        return state.won


class HeroAnim:
    """Which way the hero faces and his walk cycle, worked out from how his position changes (the 2600 hero
    is just a square). Any sideways movement -> side view ("left"/"right"); pure up/down -> back/front view
    ("up"/"down"). frame() is 0 standing, alternating 0/1 while walking."""

    def __init__(self) -> None:
        self.prev: tuple[int, int, int] | None = None   # (room, x, y) last frame
        self.view, self.moving_for, self.still_for = "down", 0, 0

    def update(self, state: GameState) -> None:
        position = (state.room_num, *state.hero)
        if self.prev and position[0] == self.prev[0]:
            dx, dy = position[1] - self.prev[1], position[2] - self.prev[2]
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
        self.prev = position

    def frame(self) -> int:
        if not self.moving_for:
            return 0
        return (self.moving_for // 8) % 2  # a stride every 8 frames of walking


def dragon_pose(dragon_state: int) -> str:
    """A dragon's state byte -> its pose: "dead" (1), "normal" (0, or 2 = it has eaten the hero), "roar"
    (anything higher: attacking, jaws open). From the game's MoveDragon routine."""
    if dragon_state == 1:
        return "dead"
    if dragon_state in (0, 2):
        return "normal"
    return "roar"


def original_graphic(obj: dict[str, Any], object_state: int, nes_colour: int | None = None,
                     col_w: int = L.COL_W) -> Picture:
    """An object's own 2600 graphic as an RGBA sprite: each bit col_w/4 * its width px wide, each row 2 px
    tall, in one NES colour, with a 1 px black outline."""
    rows = O.graphic_for_state(obj, object_state)  # one byte per row, 8 bits across
    bit_width = max(1, int(round(col_w / 4 * obj["width"])))
    width, height = 8 * bit_width + 2, 2 * len(rows) + 2  # + a 1 px outline all round
    mask = np.zeros((height, width), bool)
    for row, byte in enumerate(rows):
        for bit in range(8):
            if (byte >> (7 - bit)) & 1:
                left = 1 + bit * bit_width
                mask[1 + 2 * row:3 + 2 * row, left:left + bit_width] = True
    neighbours = np.roll(mask, 1, 0) | np.roll(mask, -1, 0) | np.roll(mask, 1, 1) | np.roll(mask, -1, 1)
    outline = neighbours & ~mask
    if nes_colour is None:
        nes_colour = PAL.ORIGINAL_TO_NES.get(obj["colour"] & 0xFE, 0x30)
    sprite = np.zeros((height, width, 4), np.uint8)
    sprite[mask] = (*PAL.NES[nes_colour], 255)
    sprite[outline] = (*PAL.NES[PAL.BLACK], 255)
    return sprite


class RoomLook(Look):
    """A look in the whole-room layout (shared/layout.py), showing a cast in a world. Supplies draw() and
    actors(); a subclass supplies its platform through the methods marked PLATFORM.

    platform       the look's key (`--look`)
    platform_name  its label in the grid view
    own_pack       the pack whose cast and world it shows unless others are chosen (--cast / --world, C / W)
    SPLASH_AFTER   frames of win_banner over the room before win_splash takes over (if it returns a screen)
    """

    platform: str = "?"
    platform_name: str = "?"
    own_pack: str = "classic"
    SPLASH_AFTER = 90

    # (platform, world, room number, light) -> the room as this platform shows it (shared by every look;
    # a look whose rooms depend on more than these keeps its own)
    scenery: dict[tuple[str, str, int, float], Picture] = {}

    def __init__(self, reader: O.Reader, cast: Cast, world: World):
        """reader: the ROM's object table (Game().reader) - which graphic and size each object has.
        cast, world: content/cast.py, content/world.py - the cast's pictures go through adapt() once, here."""
        self.reader = reader
        self.cast, self.world = cast, world
        self.key = (self.platform + ("" if cast.key == self.own_pack else f"+{cast.key}")
                    + ("" if world.key == self.own_pack else f"@{world.key}"))
        self.name = " - ".join([self.platform_name] + [part.name for part in (cast, world)
                                                       if part.key != self.own_pack])
        self.anim = HeroAnim()
        self.sprite_cache: dict[tuple[Any, ...], Picture | None] = {}
        self.current_state: GameState | None = None  # the frame being drawn (for the credit's colours)
        self.won_at: int | None = None
        self.pal_2600: dict[int, Rgb] = P.load()
        self.nearest: dict[tuple[int, ...], int] = {}   # a 2600 colour -> its nearest NES colour
        yy, xx = np.mgrid[0:L.ROOM_H, 0:L.ROOM_W]
        self.grid_yx = (yy, xx)
        self.hero = {view: [self.adapt(frame) for frame in frames] for view, frames in cast.hero().items()}
        self.dragons = {pose_colour: self.adapt(picture) for pose_colour, picture in cast.villains().items()}
        self.bat = {wings: self.adapt(picture) for wings, picture in cast.bat().items()}
        self.items = cast.items()  # adapted when drawn: a flashing item changes colour every few frames
        self.flashes: set[int] = set()  # items with pixels that flash
        for object_number, art in self.items.items():
            if np.all(art[..., :3] == FLASH, axis=2).any():
                self.flashes.add(object_number)

    # ---- PLATFORM: what a subclass supplies --------------------------------------------------------------

    def adapt(self, sprite: Picture) -> Picture:
        """The platform's rules for a cast's picture (an RGBA array) -> the picture as this look shows it:
        e.g. snapped to the NES's colours. Called once per picture (and per flash colour). Default: as is."""
        return sprite

    def adapt_scenery(self, picture: Picture) -> Picture:
        """The platform's rules for the world's pictures - rooms (RGB) and gates (RGBA). Called once per room
        and gate size. Default: as is."""
        return picture

    def object_sprite(self, object_number: int, object_state: int, box_w: float, box_h: float,
                      frame_no: int) -> Picture | None:
        """Any object other than the hero and dragons (objects.py numbers them: 09 sword, 0A bridge, 0B-0D
        keys, 0E bat, 10 chalice, 11 magnet, 01-03 castle gates...). box_w, box_h: the original's size in
        room pixels - the bridge and gates should fill it. RGBA, drawn centred on the original's box.
        This one gives the cast's (and the world's gates); a look can add stand-ins by overriding it and
        asking super() first. None = draw the original graphic."""
        if object_number == BAT:  # wings up or down: the same rule as the ROM's bat states
            wings = "up" if object_state <= 3 else "down"
            return self.bat.get(wings)
        if object_number == BRIDGE:
            return self.bridge_sprite(int(box_h), int(round(box_w)))
        if object_number in CASTLES:
            return self.gate_sprite(object_number, int(round(box_w)), int(box_h))
        if object_number in self.items:
            return self.item_sprite(object_number, frame_no)
        return None

    def gate_sprite(self, object_number: int, w: int, h: int) -> Picture | None:
        """A castle's gate, at its current height h (0 = fully open: nothing to draw)."""
        key = ("gate", object_number, w, h)
        if key not in self.sprite_cache:
            gate = self.world.gate(CASTLES[object_number], w, h) if h > 0 else None
            self.sprite_cache[key] = None if gate is None else self.adapt_scenery(gate)
        return self.sprite_cache[key]

    def item_sprite(self, object_number: int, frame_no: int) -> Picture | None:
        """The cast's picture of an item, in this frame's colour if it flashes."""
        art = self.items[object_number]
        flash = None
        if object_number in self.flashes:  # this frame's flashing colour
            flash = self.obj_colour(object_number, frame_no)
            if flash is None:
                flash = PAL.flash_colour(frame_no)
        key = ("item", object_number, flash)
        if key not in self.sprite_cache:
            if flash is not None:
                art = self.flashing(art, flash)
            self.sprite_cache[key] = self.adapt(art)
        return self.sprite_cache[key]

    def bridge_sprite(self, h: int, w: int | None = None) -> Picture | None:
        """The bridge, h pixels long (centred in w if given): the cast's, adapted; None = the original."""
        key = ("bridge", h, w)
        if key not in self.sprite_cache:
            bridge = self.cast.bridge(h, w)
            self.sprite_cache[key] = None if bridge is None else self.adapt(bridge)
        return self.sprite_cache[key]

    @abstractmethod
    def draw_hud(self, screen: Picture, state: GameState, frame_no: int) -> None:
        """The status bar: everything above ROOM_RECT on `screen` (paint it in place)."""

    @abstractmethod
    def title_screen(self, state: GameState, frame_no: int) -> Picture:
        """The whole screen for the game-select room (state.on_title_screen). Return a new RGB array."""

    @abstractmethod
    def win_banner(self, screen: Picture, state: GameState, frame_no: int) -> None:
        """Painted over the room when the game is won (state.won)."""

    def win_splash(self, state: GameState, frame_no: int) -> Picture | None:
        """A full-screen victory picture, shown SPLASH_AFTER frames after the win; None = keep the banner."""
        return None

    def unlit(self, room: Picture, light: Floats) -> Picture:
        """A dark room away from the torch: light is 0..1 per pixel (h, w). Default: fading to black."""
        return (room * light[..., None]).astype(np.uint8)

    def carried_on_top(self, object_number: int) -> bool:
        """Draw the held item over the hero (True) or under him, like the original (False)?"""
        return False

    # ---- shared machinery ---------------------------------------------------------------------------------

    def room_image(self, room: Room, light: float = 1.0) -> Picture:
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

    def hero_sprite(self, view: str, frame: int) -> Picture:
        """The hero: view is "down" / "up" / "left" / "right", frame 0 (standing) or 1 (stride). RGBA."""
        return self.hero[view][frame]

    def dragon_sprite(self, pose: str, colour: str) -> Picture | None:
        """A dragon: pose "normal" / "roar" / "dead", colour "red" / "yellow" / "green". RGBA, drawn centred
        on the original dragon with its feet on the bottom of the original's box. None = draw the original."""
        return self.dragons.get((pose, colour))

    @staticmethod
    def flashing(sprite: Picture, colour: int) -> Picture:
        """The sprite with its FLASH pixels (content/pictures.py) in NES colour `colour`."""
        mark = np.all(sprite[..., :3] == FLASH, axis=2) & (sprite[..., 3] > 0)
        if not mark.any():
            return sprite
        out = sprite.copy()
        out[mark, :3] = PAL.NES[colour]
        return out

    def held_icon(self, object_number: int, frame_no: int) -> Picture:
        """The carried object as the status bar's item box shows it (fitted to 12 px; the bridge 24 px)."""
        if object_number == BRIDGE:
            sprite = self.bridge_sprite(24)
        else:
            sprite = self.object_sprite(object_number, 0, 12, 12, frame_no)
        if sprite is None:
            sprite = self.original_sprite(object_number, 0, frame_no)
        return sprite

    def obj_colour(self, object_number: int, frame_no: int) -> int | None:
        """The NES colour for a flashing object (odd 2600 colour) this frame, else None."""
        colour_byte = self.reader.objects[object_number]["colour"]
        if not colour_byte & 1:  # an even colour doesn't flash
            return None
        if object_number == AUTHOR and self.current_state is not None:
            # exactly what the 2600 shows this frame (its ChangeColor routine)
            rgb = tuple(self.pal_2600[self.current_state.colour(colour_byte) & 0xFE])
            if rgb not in self.nearest:
                self.nearest[rgb] = PAL.nearest_nes(rgb)
            return self.nearest[rgb]
        return PAL.flash_colour(frame_no)

    def original_sprite(self, object_number: int, object_state: int, frame_no: int) -> Picture:
        """The object's own 2600 graphic (cached) - for anything the art methods don't draw."""
        colour = self.obj_colour(object_number, frame_no)
        key = (object_number, object_state, colour)
        if key not in self.sprite_cache:
            obj = self.reader.objects[object_number]
            self.sprite_cache[key] = original_graphic(obj, object_state, nes_colour=colour)
        sprite = self.sprite_cache[key]
        assert sprite is not None   # every object has its own graphic
        return sprite

    def placed(self, object_number: int, x: int, y: int, object_state: int, frame_no: int) -> Placed:
        """An object at the game's position (x, y) -> (sprite, room-space x, y) to blit."""
        obj = self.reader.objects[object_number]
        wide_shift = 0 if obj["width"] > 1 else -1  # a single-width graphic sits one unit left
        left, top = L.to_room(x + wide_shift, scan_line(y))
        graphic_height = 2 * len(O.graphic_for_state(obj, object_state))  # 2 scan lines a row
        if object_number in DRAGON_COLOUR:
            pose = dragon_pose(object_state)
            sprite = self.dragon_sprite(pose, DRAGON_COLOUR[object_number])
            if sprite is not None:  # centred on the original 8-pixel-wide graphic, feet on its bottom
                return sprite, left + 6 - sprite.shape[1] / 2, top + graphic_height - sprite.shape[0]
        box_w = 8 * obj["width"] * L.COL_W / 4
        box_h = graphic_height
        sprite = self.object_sprite(object_number, object_state, box_w, box_h, frame_no)
        if sprite is not None:  # centred on the original's box
            return sprite, left + (box_w - sprite.shape[1]) / 2, top + (box_h - sprite.shape[0]) / 2
        sprite = self.original_sprite(object_number, object_state, frame_no)
        return sprite, left - 1, top - 1  # its 1 px outline

    @staticmethod
    def hero_centre(state: GameState) -> tuple[float, float]:
        """The middle of the hero's hit-box, in room pixels."""
        hero_x, hero_y = state.hero
        return L.to_room(hero_x, scan_line(hero_y) + HERO_HALF_HEIGHT)

    def hero_placed(self, state: GameState) -> Placed:
        """(sprite, x, y): feet on the bottom of the game's hit-box. Overlap with a wall then only happens
        upward - the head against the wall above, which reads as standing in front of it."""
        centre_x, centre_y = self.hero_centre(state)
        sprite = self.hero_sprite(self.anim.view, self.anim.frame())
        feet = centre_y + HERO_HALF_HEIGHT
        return sprite, centre_x - sprite.shape[1] / 2, feet - (sprite.shape[0] - 1 - self.cast.foot_gap)

    def carried_placed(self, state: GameState, object_number: int, x: int, y: int, object_state: int,
                       frame_no: int) -> Placed:
        """Where the held item is drawn: exactly where the game has it - moving it would make hits miss
        where they looked like they landed (the game hit-tests its own positions)."""
        return self.placed(object_number, x, y, object_state, frame_no)

    def actors(self, state: GameState, frame_no: int) -> dict[str, Placed]:
        out: dict[str, Placed] = {}
        for object_number, x, y, object_state in state.objects:
            if object_number == state.carried:
                out["item"] = self.carried_placed(state, object_number, x, y, object_state, frame_no)
        if "item" in out and self.carried_on_top(state.carried):
            return {"hero": self.hero_placed(state), **out}
        out["hero"] = self.hero_placed(state)
        return out

    def draw(self, state: GameState, frame_no: int, actors: bool = True) -> Picture:
        self.anim.update(state)
        self.current_state = state
        if state.on_title_screen:
            return self.title_screen(state, frame_no)
        light = self.world.lighting(state.room_num, frame_no)
        room = self.room_image(state.room, light).copy()
        self.draw_objects(room, state, frame_no, actors)
        if state.room["colour"] == DARK_ROOM_COLOUR:
            room = self.torch_lit(room, state)
        screen = np.zeros((L.SCREEN_H, L.SCREEN_W, 3), np.uint8)
        x0, y0, w, h = self.ROOM_RECT
        screen[y0:y0 + h, x0:x0 + w] = room
        self.draw_hud(screen, state, frame_no)
        if not self.won(state):
            self.won_at = None
            return screen
        return self.winning(screen, state, frame_no)

    def draw_objects(self, room: Picture, state: GameState, frame_no: int, actors: bool) -> None:
        """Every object where the game has it, then the hero; the held item is drawn in its place among the
        objects (under the hero, like the original) or after him if this look carries it on top.
        actors=False leaves out the hero and his item (a room scroll draws those itself)."""
        highest_number_first = sorted(state.objects, key=lambda item: -item[0])
        for object_number, x, y, object_state in highest_number_first:
            if object_number == SURROUND:
                continue
            if object_number != state.carried:
                blit(room, *self.placed(object_number, x, y, object_state, frame_no))
            elif actors and not self.carried_on_top(object_number):
                blit(room, *self.carried_placed(state, object_number, x, y, object_state, frame_no))
        if not actors:
            return
        blit(room, *self.hero_placed(state))
        for object_number, x, y, object_state in state.objects:
            if object_number == state.carried and self.carried_on_top(object_number):
                blit(room, *self.carried_placed(state, object_number, x, y, object_state, frame_no))

    def torch_lit(self, room: Picture, state: GameState) -> Picture:
        """A dark room: only a torch light around the hero shows it, in 3 bands of brightness."""
        centre_x, centre_y = self.hero_centre(state)
        yy, xx = self.grid_yx
        distance = np.hypot(xx - centre_x, (yy - centre_y) * 0.9)  # a slightly tall circle
        brightness = np.clip(1.35 - distance / 34.0, 0, 1)        # full near him, nothing ~46 px away
        banded = np.round(brightness * 3) / 3
        return self.unlit(room, banded)

    def winning(self, screen: Picture, state: GameState, frame_no: int) -> Picture:
        """The game is won: the win banner over the room, then (after SPLASH_AFTER frames) the splash."""
        if self.won_at is None:
            self.won_at = frame_no
        if frame_no - self.won_at >= self.SPLASH_AFTER:
            splash = self.win_splash(state, frame_no)
            if splash is not None:
                return splash
        self.win_banner(screen, state, frame_no)
        return screen
