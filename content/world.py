"""A WORLD: where the game happens - how each of the game's places looks (its walls, floor and castle gates),
what it's called, and the word in the title - as tile pictures in a pack's world/ folder, plus pack.json.

Every look shows every world, adapting its rooms to the look's rules (docs/platform-rules.md). The game
decides where the walls are; a world only decides what they're made of.

THE PLACES (AREAS below) are the game's own, so they mean the same in every world:
    meadow, gold_castle, gold_castle_inside, labyrinth (the blue maze), catacombs, white_castle,
    white_castle_inside, black_castle, black_castle_inside, black_maze, red_maze, purple_room, credit_room

THE PICTURES - tiles, repeated across a room (any size; a tile that repeats seamlessly looks best):
    wall_<place>.png   floor_<place>.png    one place's walls and floor
    wall.png           floor.png            every place without its own
    gate_<castle>.png  gate.png             a castle's gate (gold / white / black), cut to the gate's opening
Without a wall tile, walls are the game's own colour for that room; without a floor tile, the floor is grey.

pack.json "world" (every field optional):
    name         shown in --list and the grid view                  "THE CASTLES"
    title_small  the small word after ADVENTURE on the title        "FOREVER"
    footer       the last line of the title screen
    outline      a line around the walls, [r, g, b]                 [0, 0, 0]
    shadow       how dark the walls' shadow on the floor is, 0-1    0.6
    areas        per place: its tiles (picture names), its name in the status bar, its colour on screens
                 {"red_maze": {"wall": "wall_red", "floor": "floor_flag", "name": "RED MAZE",
                               "colour": [r, g, b]},
                  "default": {...the same, for every place not listed}}
    ambience     per place, what you hear with the music off (engine/ambience.py: summer, woods, hall,
                 cave, embers, frost); "default" for every place not listed; none: silence
                 {"meadow": "summer", "catacombs": "cave", "default": "summer"}
    extends      another pack's world to start from: its scenery, with this world's names
    scale        the tiles are drawn this many times bigger than the room's pixels

A SOUNDTRACK (optional): world/music.json - songs in engine/chiptune.py's notation, and which plays where:
    {"synth": "fm" (engine/fm.py, an early-90s PC sound) or "chiptune" (the NES-style built-in synth),
     "areas": {"title" / "overworld" / "dungeon" / "final" / "win": song name},
     "songs": {name: {"bpm": ..., "chords": ..., "melody": ..., "drums": ..., "style": ..., "loop": ...}}}
It plays while the world is on screen (engine/music.py); N cycles to the other music sources.

Scenery pictures can't express (rounded walls, scattered flowers): add world.py to the world/ folder,
defining `class CustomWorld(World)` - it's made like a World and overrides room(), gate() or colour().
"""

import copy
import json
import os

from typing import Any

import numpy as np

from content import pictures as PIC
from engine import palette as P
from shared import layout as L
from shared.types import Picture, Rgb

Room = dict[str, Any]   # engine/rooms.py's decoded room: its walls grid, colour, exits, flags

AREAS = {  # the game's places -> their rooms
    "meadow": (0x01, 0x02, 0x0D),
    "gold_castle": (0x03, 0x11), "gold_castle_inside": (0x12,),
    "labyrinth": (0x04, 0x05, 0x06, 0x07, 0x08, 0x0C, 0x0E),
    "catacombs": (0x09, 0x0A, 0x0B),
    "white_castle": (0x0F,), "white_castle_inside": (0x1A,),
    "black_castle": (0x10,), "black_castle_inside": (0x1B,),
    "black_maze": (0x13, 0x14, 0x15, 0x16),
    "red_maze": (0x17, 0x18, 0x19, 0x1D),
    "purple_room": (0x1C,), "credit_room": (0x1E,),
}
AREA_OF = {room: area for area, rooms in AREAS.items() for room in rooms}
CASTLES = {0x01: "gold", 0x02: "white", 0x03: "black"}  # gate object -> its castle
DEFAULT_NAMES = {
    "meadow": "THE MEADOW", "gold_castle": "GOLD CASTLE", "gold_castle_inside": "GOLD CASTLE HALL",
    "labyrinth": "BLUE LABYRINTH", "catacombs": "CATACOMBS", "white_castle": "WHITE CASTLE",
    "white_castle_inside": "WHITE CASTLE HALL", "black_castle": "BLACK CASTLE",
    "black_castle_inside": "BLACK CASTLE HALL", "black_maze": "BLACK MAZE", "red_maze": "RED MAZE",
    "purple_room": "PURPLE ROOM", "credit_room": "PURPLE ROOM"}  # the hidden credit: no spoiler
FLOOR = (170, 170, 170)  # the 2600's own grey
BRIGHTNESS = [0.299, 0.587, 0.114]  # how bright red, green and blue look


def area(room_num: int) -> str:
    """The place a room belongs to."""
    return AREA_OF.get(room_num, "meadow")


def paint_tiles(room: Room, wall: Picture | None = None, floor: Picture | None = None,
                outline: Rgb | None = None, shadow: float | None = None, wall_colour: Rgb = (128, 128, 128),
                col_w: int = L.COL_W) -> Picture:
    """A room from tiles: `floor` everywhere, `wall` where the game has walls (both RGB tiles, repeated from
    the room's top-left), an `outline` colour around the walls, the floor under each wall darkened to
    `shadow` (0-1) for two rows. No wall tile: `wall_colour`. No floor tile: grey. col_w: pixels per wall
    column (the room layout's 6)."""
    walls = L.wall_mask(room, col_w)
    h, w = walls.shape
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = FLOOR if floor is None else floor[yy % floor.shape[0], xx % floor.shape[1]]
    if wall is None:
        img[walls] = wall_colour
    else:
        img[walls] = wall[yy % wall.shape[0], xx % wall.shape[1]][walls]
    if outline is not None:
        above_below = np.roll(walls, 1, 0) & np.roll(walls, -1, 0)
        either_side = np.roll(walls, 1, 1) & np.roll(walls, -1, 1)
        edge = walls & ~(above_below & either_side)  # wall pixels next to floor
        img[edge] = outline
    if shadow is not None:
        under = ~walls & (np.roll(walls, 1, 0) | np.roll(walls, 2, 0))  # the two rows of floor below a wall
        img[under] = (np.array(img[under], int) * shadow).astype(np.uint8)
    return img


class World:
    """A world, loaded. Looks use only the attributes and methods here."""

    def __init__(self, key: str, folder: str, info: dict[str, Any]):
        """key: the pack's; folder: its world/ folder; info: pack.json's "world" section."""
        self.key, self.folder, self.info = key, folder, info
        self.name: str = info.get("name", key.upper())
        self.title_small: str = info.get("title_small", "FOREVER")
        self.footer: str = info.get("footer", "")
        outline = info.get("outline")
        self.outline: Rgb | None = (outline[0], outline[1], outline[2]) if outline else None
        self.shadow: float | None = info.get("shadow")
        self.areas: dict[str, dict[str, Any]] = info.get("areas", {})
        self.ambience: dict[str, str] = info.get("ambience", {})
        self.pictures: dict[str, Picture] = PIC.load_folder(folder, info.get("scale", 1))
        self.music: dict[str, Any] | None = None  # the soundtrack, if the world has one (music.json)
        if os.path.exists(os.path.join(folder, "music.json")):
            with open(os.path.join(folder, "music.json")) as f:
                self.music = json.load(f)
        self.palette_2600: dict[int, Rgb] = P.load()
        self.rooms: dict[int, Picture] = {}  # room number -> picture: rooms never change

    def extended(self, key: str, info: dict[str, Any]) -> "World":
        """This world's scenery under another pack's key and words (pack.json "extends")."""
        out = copy.copy(self)
        out.key, out.info = key, {**self.info, **info}
        out.name = info.get("name", key.upper())
        out.title_small = info.get("title_small", self.title_small)
        out.footer = info.get("footer", self.footer)
        out.ambience = {**self.ambience, **info.get("ambience", {})}
        its_areas = info.get("areas", {})
        out.areas = {}
        for place in {*self.areas, *its_areas}:  # this world's settings over the original's, place by place
            out.areas[place] = {**self.areas.get(place, {}), **its_areas.get(place, {})}
        return out

    def setting(self, place: str, what: str) -> Any:
        """pack.json's areas[place][what], else areas["default"][what], else None."""
        return self.areas.get(place, {}).get(what, self.areas.get("default", {}).get(what))

    def tile(self, place: str, kind: str) -> Picture | None:
        """The `kind` ("wall" / "floor") tile for a place, RGB, or None."""
        name = self.setting(place, kind)
        pic = self.pictures.get(name) if name else None
        if pic is None:
            pic = self.pictures.get(f"{kind}_{place}", self.pictures.get(kind))
        return None if pic is None else pic[..., :3]

    # ---- what looks ask for ----------------------------------------------------------------------------

    def room(self, room: Room) -> Picture:
        """The room's walls and floor: a 240x192 RGB picture (room: engine/rooms.py's decoded room)."""
        room_number = room["room"]
        if room_number not in self.rooms:
            place = area(room_number)
            original_colour = self.palette_2600[room["colour"] & 0xFE]
            self.rooms[room_number] = paint_tiles(room, self.tile(place, "wall"), self.tile(place, "floor"),
                                                  self.outline, self.shadow, original_colour)
        return self.rooms[room_number]

    def area_name(self, room_num: int) -> str:
        """What the status bar calls this room's place."""
        place = area(room_num)
        return self.areas.get(place, {}).get("name") or DEFAULT_NAMES[place]

    def colour(self, room_num: int) -> Rgb:
        """The place's colour, for screens to frame it with (on a dark bar, so never too dark): pack.json's,
        else the brightest of its wall tile's three commonest colours."""
        place = area(room_num)
        chosen = self.setting(place, "colour")
        if chosen:
            return chosen[0], chosen[1], chosen[2]
        wall = self.tile(place, "wall")
        if wall is None:
            return (200, 200, 200)
        colours, counts = np.unique(wall.reshape(-1, 3).astype(int), axis=0, return_counts=True)
        commonest = colours[np.argsort(-counts)[:3]]
        colour = commonest[np.argmax(commonest @ BRIGHTNESS)]
        brightness = colour @ BRIGHTNESS
        if brightness < 120:  # lift a dark colour towards white until it reads
            colour = colour + (255 - colour) * (120 - brightness) / (255 - brightness)
        return int(colour[0]), int(colour[1]), int(colour[2])

    def gate(self, castle: str, w: int, h: int) -> Picture | None:
        """A castle's gate ("gold" / "white" / "black"), w x h, RGBA - the bottom of the gate picture,
        repeated across; None = the original gate."""
        pic = self.pictures.get(f"gate_{castle}", self.pictures.get("gate"))
        if pic is None or h <= 0 or w <= 0:
            return None
        reps = (-(-h // pic.shape[0]), -(-w // pic.shape[1]), 1)
        return np.tile(pic, reps)[-h:, :w]

    def lighting(self, room_num: int, frame_no: int) -> float:
        """How lit a room is this frame, 0-1: 1 = as painted (the default, always). A world with flickering
        lights returns less now and then; the look shows the room dimmed (kept to its own colour rules)."""
        return 1.0

    def sound(self, room_num: int) -> str | None:
        """What you hear in a room with the music off (one of engine/ambience.py's SOUNDS), or None."""
        return self.ambience.get(area(room_num), self.ambience.get("default"))

    def wall_tile(self, room_num: int) -> Picture | None:
        """The wall tile of a room's place (for screens that draw a miniature castle), or None."""
        return self.tile(area(room_num), "wall")
