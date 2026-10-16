"""The game's state, as the looks see it.

The 2600 keeps the whole game in 128 bytes of RAM (see ram_map.py). Every frame the app takes a snapshot of
those bytes and wraps it in a GameState: named fields - which room, where the hero is, what he carries, every
object in the room, whether the game is won - so a look never needs to know a RAM address.

    game = Game()                  # once: reads the ROM's rooms and object tables
    st = game.state(core.ram)      # every frame: a snapshot of the RAM, decoded
    st.room_num, st.hero, st.carried, st.objects, st.won, st.eaten_by, st.game, st.on_title_screen
"""

from engine import objects as O
from engine import palette as P
from engine import ram_map as M
from engine import rooms as R

DRAWN_OBJECTS = range(0x00, 0x12)  # every object but "null"
DRAGON_COLOURS = {M.RED_DRAGON: "red", M.YELLOW_DRAGON: "yellow", M.GREEN_DRAGON: "green"}


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

    def __init__(self, ram, reader, room_table):
        r = lambda addr: int(ram[addr - 0x80])
        self.ram = ram
        # Right after power-on, before the game has set up its RAM, the bytes are whatever the console
        # powered up with (random, on real hardware and on newer Stella cores): an impossible room or item
        # is read as "still starting up" - the title screen, nothing carried - never as an error.
        self.room_num = r(M.ROOM) if r(M.ROOM) < len(room_table) else M.NUMBER_ROOM
        self.room = room_table[self.room_num]
        self.hero = (r(M.X), r(M.Y))
        self.carried = r(M.CARRIED) // 9 if r(M.CARRIED) // 9 < len(reader.objects) else M.NOTHING_CARRIED // 9
        self.game = min(r(M.LEVEL) // 2, 2) + 1
        self.on_title_screen = self.room_num == M.NUMBER_ROOM
        self.won = not self.on_title_screen and r(M.GAME_ACTIVE) != 0  # only a win sets it (being eaten doesn't)
        self.eaten_by = next((colour for addr, colour in DRAGON_COLOURS.items()
                              if r(addr + M.DRAGON_STATE_OFFSET) == 2), None)
        self.objects = []  # (num, x, y, state)
        for n in DRAWN_OBJECTS:
            room, x, y = reader.where(ram, n)
            if room != self.room_num:
                continue
            if n == self.carried:  # carried: always exactly hero + offset (the game applies it a step late)
                x = (self.hero[0] + r(M.CARRY_DX)) & 0xFF
                y = (self.hero[1] + r(M.CARRY_DY)) & 0xFF
            self.objects.append((n, x, y, reader.state(ram, n)))

    def colour(self, value):
        """The game's ChangeColor ($F2D3): a 2600 colour as the game shows it this frame - odd values flash
        (their colour comes from RAM, usually the frame counter), and attract mode dims everything."""
        a = value >> 1
        if value & 1:
            a = int(self.ram[a])  # $80 + a, i.e. usually $E5 (the frame counter)
        e6 = int(self.ram[0xE6 - 0x80])
        if e6 & 0x80:
            a = (a ^ e6) & 0xFB
        return (a << 1) & 0xFF


class Game:
    """What the ROM says about the world - read once: the rooms, the object table, the 2600 palette."""

    def __init__(self):
        self.rom = R.load_rom()
        self.rooms = R.decode_all(self.rom)
        self.reader = O.Reader(self.rom)
        self.palette = P.load()

    def state(self, ram):
        """A GameState from the 128 RAM bytes (copied - the emulator's RAM is live)."""
        return GameState(ram.copy(), self.reader, self.rooms)

    def rgb(self, colour):
        """A 2600 colour number -> (r, g, b) as the Stella core shows it."""
        return self.palette[colour & 0xFE]
