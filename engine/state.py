"""The game's state, as the looks see it.

The 2600 keeps the whole game in 128 bytes of RAM (see ram_map.py). Every frame the app takes a snapshot of
those bytes and wraps it in a GameState: named fields - which room, where the hero is, what he carries, every
object in the room, whether the game is won - so a look never needs to know a RAM address.

    game = Game()                  # once: reads the ROM's rooms and object tables
    st = game.state(core.ram)      # every frame: a snapshot of the RAM, decoded
    st.room_num, st.hero, st.carried, st.objects, st.won, st.eaten_by, st.game, st.on_title_screen
"""

from typing import Any, NamedTuple

from engine import objects as O
from engine import palette as P
from engine import ram_map as M
from engine import rooms as R
from shared.types import Point, RamBytes, RamView, Rgb

DRAWN_OBJECTS = range(0x00, 0x12)  # every object but "null"
DRAGON_COLOURS = {M.RED_DRAGON: "red", M.YELLOW_DRAGON: "yellow", M.GREEN_DRAGON: "green"}


class RoomObject(NamedTuple):
    """An object in the hero's room (engine/objects.py numbers them)."""
    number: int
    x: int
    y: int
    state: int        # its state byte: a dragon's mood, a gate's height... (0 for most)


class GameState:
    """One frame of the game. Built by Game.state(ram); the RAM is copied, so it never changes afterwards.

    room_num         the room the hero is in ($00 = the game-select screen)
    room             that room's decoded data (rooms.py): walls grid, colour, exits, flags
    hero             (x, y) in the game's units - y counts UP from the bottom of the room
    carried          the object number the hero holds ($12 = nothing)
    objects          [(number, x, y, state)] for every object in the hero's room (objects.py numbers them)
    game             1, 2 or 3
    won              the chalice is home - the game's own flag, set once and frozen until RESET
    eaten_by         "red" / "yellow" / "green" while a dragon has the hero in its stomach, else None
    on_title_screen  the game-select screen (room $00)
    ram              the 128 bytes themselves, indexed from $80 - for the RAM panel, not for looks
    """

    def __init__(self, ram: RamBytes, reader: O.Reader, room_table: list[dict[str, Any]]):
        def byte(addr: int) -> int:  # the RAM byte at a 2600 address ($80-$FF)
            return int(ram[addr - 0x80])
        self.ram: RamBytes = ram
        # Right after power-on, before the game has set up its RAM, the bytes are whatever the console
        # powered up with (random, on real hardware and on newer Stella cores): an impossible room or item
        # is read as "still starting up" - the title screen, nothing carried - never as an error.
        room_num = byte(M.ROOM)
        self.room_num: int = room_num if room_num < len(room_table) else M.NUMBER_ROOM
        self.room: dict[str, Any] = room_table[self.room_num]
        self.hero: Point = (byte(M.HERO_X), byte(M.HERO_Y))
        carried = byte(M.CARRIED) // 9  # the game keeps the object number times 9
        self.carried: int = carried if carried < len(reader.objects) else M.NOTHING_CARRIED // 9
        self.game: int = min(byte(M.LEVEL) // 2, 2) + 1
        self.on_title_screen: bool = self.room_num == M.NUMBER_ROOM
        # only a win sets the flag (being eaten doesn't)
        self.won: bool = not self.on_title_screen and byte(M.GAME_ACTIVE) != 0
        self.eaten_by: str | None = None
        for addr, colour in DRAGON_COLOURS.items():
            if byte(addr + M.DRAGON_STATE_OFFSET) == 2:  # 2: this dragon has eaten the hero
                self.eaten_by = colour
                break
        self.objects: list[RoomObject] = []
        for object_number in DRAWN_OBJECTS:
            room, x, y = reader.where(ram, object_number)
            if room != self.room_num:
                continue
            if object_number == self.carried:  # exactly hero + offset (the game applies it a step late)
                x = (self.hero[0] + byte(M.CARRY_DX)) & 0xFF
                y = (self.hero[1] + byte(M.CARRY_DY)) & 0xFF
            self.objects.append(RoomObject(object_number, x, y, reader.state(ram, object_number)))

    def colour(self, value: int) -> int:
        """The game's ChangeColor ($F2D3): a 2600 colour as the game shows it this frame - odd values flash
        (their colour comes from RAM, usually the frame counter), and attract mode dims everything."""
        colour = value >> 1
        if value & 1:
            colour = int(self.ram[colour])  # the byte at $80 + colour: usually $E5 (the frame counter)
        attract = int(self.ram[0xE6 - 0x80])  # the attract-mode (screen saver) byte
        if attract & 0x80:
            colour = (colour ^ attract) & 0xFB
        return (colour << 1) & 0xFF


class Game:
    """What the ROM says about the world - read once: the rooms, the object table, the 2600 palette."""

    def __init__(self) -> None:
        self.rom: bytes = R.load_rom()
        self.rooms: list[dict[str, Any]] = R.decode_all(self.rom)
        self.reader: O.Reader = O.Reader(self.rom)
        self.palette: dict[int, Rgb] = P.load()

    def state(self, ram: RamView) -> GameState:
        """A GameState from the 128 RAM bytes (copied - the emulator's RAM is live)."""
        return GameState(ram.copy(), self.reader, self.rooms)

    def rgb(self, colour: int) -> Rgb:
        """A 2600 colour number -> (r, g, b) as the Stella core shows it."""
        return self.palette[colour & 0xFE]
