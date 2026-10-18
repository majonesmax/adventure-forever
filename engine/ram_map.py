"""What the 128 bytes of Adventure's RAM mean - the game state our renderer reads every frame.

Source: the commented disassembly by Joel D. Park, as converted by Andy McFadden
(https://6502disassembly.com/2600-adventure/), then checked live against the running game (verify_ram.py).

The heart is Robinett's "object list": on RESET the game copies a 49-byte table from ROM ($F460 for game 1,
$F491 for games 2/3) into RAM $A1-$D1. Every movable thing lives there as (room, x, y[, movement, state]).
Coordinates are the game's own units; y counts UP from the bottom of the room. The mapping to screen pixels
is calibrated in step 3/4 (drawing boxes over the real frame).
"""

# --- the hero (the "ball" in the disassembly - he is drawn with the TIA's ball graphic) -------------
ROOM, HERO_X, HERO_Y = 0x8A, 0x8B, 0x8C  # the hero: current room, x, y
PREV_ROOM, PREV_X, PREV_Y = 0xE2, 0xE3, 0xE4  # last position that didn't hit a wall (bounce-back target)
CARRIED = 0x9D                          # object being carried, as object number * 9 (see OBJECTS); $A2 = none
NOTHING_CARRIED = 0xA2                  # = object $12 ("null") * 9
CARRY_DX, CARRY_DY = 0x9E, 0x9F         # item offset from the hero, fixed at pickup; item = hero + offset
                                        # (applied by MoveCarriedObject, a step after the hero moves)

# --- game / console ----------------------------------------------------------------------------------
LEVEL = 0xDD           # 0, 2, 4 = game 1, 2, 3
GAME_ACTIVE = 0xDE     # 0 while playing; $FF once the chalice is home (the WIN - being eaten leaves it 0,
                       # verified 2026-10-14); RESET clears it
SWITCHES = 0x92        # last read of the console switches (edge detection for SELECT)
RANDOM = 0xE5          # "low input counter", the game-3 random seed
JOY_RAW, JOY_COOKED = 0x99, 0x9B  # joystick this frame (raw SWCHA) and after removing blocked directions

# --- the object list ($A1-$D1) -------------------------------------------------------------------------
# name -> (room address, has movement+state bytes)
DOT = 0xA1             # the hidden grey dot (room, x, y)
RED_DRAGON = 0xA4      # Rhindle  (room, x, y, movement, state)
YELLOW_DRAGON = 0xA9   # Yorgle   (room, x, y, movement, state)
GREEN_DRAGON = 0xAE    # Grundle  (room, x, y, movement, state)
MAGNET = 0xB3
SWORD = 0xB6
CHALICE = 0xB9
BRIDGE = 0xBC
YELLOW_KEY = 0xBF
WHITE_KEY = 0xC2
BLACK_KEY = 0xC5
PORTCULLIS = (0xC8, 0xC9, 0xCA)  # gate state: gold castle (room $11), white ($0F), black ($10)
BAT = 0xCB             # (room, x, y, movement, state)
BAT_CARRYING, BAT_FED_UP = 0xD0, 0xD1

DRAGON_STATE_OFFSET = 4  # room + 4 = state (disassembly MoveDragon): $00 normal, $01 dead, $02 has eaten
                         # the hero (normal graphic), $03-$FF roaring = jaws open (attack)

# Object numbers as the ROM's object table ($FF44, 9 bytes each) numbers them. CARRIED holds number * 9.
OBJECTS = {0x00: "surround", 0x01: "portcullis 1", 0x02: "portcullis 2", 0x03: "portcullis 3",
           0x04: "author name", 0x05: "game number", 0x06: "red dragon", 0x07: "yellow dragon",
           0x08: "green dragon", 0x09: "sword", 0x0A: "bridge", 0x0B: "yellow key", 0x0C: "white key",
           0x0D: "black key", 0x0E: "bat", 0x0F: "dot", 0x10: "chalice", 0x11: "magnet", 0x12: "null"}

# Items the hero can pick up, with where their (room, x, y) lives in RAM
ITEMS = {"sword": SWORD, "bridge": BRIDGE, "yellow key": YELLOW_KEY, "white key": WHITE_KEY,
         "black key": BLACK_KEY, "chalice": CHALICE, "magnet": MAGNET, "dot": DOT}
DRAGONS = {"red dragon": RED_DRAGON, "yellow dragon": YELLOW_DRAGON, "green dragon": GREEN_DRAGON}

CASTLE_ROOMS = {0x11: "gold castle", 0x0F: "white castle", 0x10: "black castle"}
NUMBER_ROOM = 0x00     # the game-select screen is "room 0"


def carried_name(ram):
    """ram = the 128-byte array indexed from $80."""
    carried = int(ram[CARRIED - 0x80])
    if carried == NOTHING_CARRIED:
        return None
    return OBJECTS.get(carried // 9, f"?{carried:02X}")


def pos(ram, addr):
    """(room, x, y) of an object-list entry."""
    i = addr - 0x80
    return int(ram[i]), int(ram[i + 1]), int(ram[i + 2])
