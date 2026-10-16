"""Which Adventure is this ROM - and will the remasters understand it?

Adventure Forever is made for the NTSC release of Adventure (Atari CX2613, also sold by Sears): every good dump
of that cartridge is the same 4096 bytes (MD5 below). Any other ROM still runs - the game is played by the
emulator either way - but the remasters read the ROM's tables at fixed places and the RAM at fixed addresses
(rooms.py, objects.py, ram_map.py). A version that moved them would be drawn wrongly, so instead of a
mysterious picture, the player is told which ROM it is and what doesn't match.

    report(rom) -> None for the supported ROM; else (headline, [detail lines]) for the window and the terminal
"""

import hashlib

from engine import objects as O
from engine import ram_map as M
from engine import rooms as R

SUPPORTED = "157bddb7192754a45372be196797f284"
KNOWN = {  # MD5 -> name, from Stella's game database
    SUPPORTED: "Adventure (1980) (Atari) - NTSC",
    "4b27f5397c442d25f0c418ccdacf1926": "Adventure (1980) (Atari) - PAL",
    "543b4b8ff1d616fa250c648be428a75c": "Adventure (1978) (Warren Robinett) - hack",
    "9be58a14e055b0e7581fc4d6c2f6b31d": "Adventure (Color Scrolling) - hack",
    "a5b7f420ca6cc1384da0fed523920d8e": "Adventure (New Graphics) - hack",
    "171cd6b55267573e6a9c2921fb720794": "Adventure 34 (Kurt Howe) - hack",
    "e923001015bedd7901569f035d9c592c": "Adventure II - hack",
    "e2846af3e4d172b251ab77cbdd01761e": "Adventure Plus (Steve Engelhardt) - hack",
    "295f3679bdf91ca5e37da3f787b29997": "Exorcise - hack of Adventure",
    "cff578e5c60de8caecbee7f2c9bbb57b": "Suicide Adventure (George Veeder) - hack",
    "e7a758bb0b43d0f7004e92b9abf4bc83": "Troll's Adventure - hack",
    "1367e41858be525710eb04d0dab53505": "Zelda (Kyle Pittman) - hack of Adventure",
}
EXPECTED_POSITION = {  # object number -> where the RAM map says its (room, x, y) lives
    0x06: M.RED_DRAGON, 0x07: M.YELLOW_DRAGON, 0x08: M.GREEN_DRAGON, 0x09: M.SWORD, 0x0A: M.BRIDGE,
    0x0B: M.YELLOW_KEY, 0x0C: M.WHITE_KEY, 0x0D: M.BLACK_KEY, 0x0E: M.BAT, 0x0F: M.DOT, 0x10: M.CHALICE,
    0x11: M.MAGNET}
EXPECTED_STATE = {0x01: M.PORTCULLIS[0], 0x02: M.PORTCULLIS[1], 0x03: M.PORTCULLIS[2], 0x05: M.LEVEL}


def md5(rom):
    return hashlib.md5(bytes(rom)).hexdigest()


def problems(rom):
    """What in this ROM's tables doesn't match what the remasters expect ([] = all fine)."""
    out = []
    objects = O.decode_all(rom)
    hexed = lambda a: f"${a:02X}" if a < 0x100 else f"${a:04X}"
    moved = [f"{O.NAMES[n]} ({hexed(objects[n]['info'])}, expected {hexed(addr)})"
             for n, addr in EXPECTED_POSITION.items() if objects[n]["info"] != addr]
    if moved:
        out.append(f"it keeps {len(moved)} of {len(EXPECTED_POSITION)} objects' positions elsewhere: "
                   + ", ".join(moved[:3]) + (f" and {len(moved) - 3} more" if len(moved) > 3 else ""))
    moved = [O.NAMES[n] for n, addr in EXPECTED_STATE.items() if objects[n]["state_ptr"] != addr]
    if moved:
        out.append("the state of the " + ", ".join(moved) + (" is" if len(moved) == 1 else " are") + " kept elsewhere")
    if any(not o["states"] or o["states"][-1][0] != 0xFF for o in objects):
        out.append("its object table doesn't look like Adventure's")
    bad_rooms = []
    for n in range(R.N_ROOMS):
        room = R.decode_room(rom, n)
        exits = [e for g in (1, 2, 3) for e in room["exits"][g].values()]
        if room["gfx"] < 0xF000 or any(e >= R.N_ROOMS for e in exits):
            bad_rooms.append(n)
    if bad_rooms:
        out.append(f"{len(bad_rooms)} of its {R.N_ROOMS} rooms don't decode as Adventure rooms (walls or exits)")
    return out


def report(rom):
    """None for the supported ROM; else (headline, details) to show the player."""
    digest = md5(rom)
    if digest == SUPPORTED:
        return None
    name = KNOWN.get(digest)
    headline = (f"This ROM is {name}" if name else "This ROM isn't a version we recognise") + \
               " - Adventure Forever is made for the NTSC release."
    found = problems(rom)
    if len(found) >= 3:  # nothing where Adventure keeps it: not Adventure at all, or a bad dump
        return (f"This ROM doesn't look like Adventure (MD5 {digest}).",
                ["It may be another game, or a damaged dump. The emulator will run whatever it is, but the",
                 "remasters can't draw it. Adventure Forever is made for the NTSC Adventure (Atari CX2613),",
                 f"MD5 {SUPPORTED}."])
    if found:
        details = ["The remasters will draw things wrongly, because " + found[0] + "."]
        details += [f"Also, {p}." for p in found[1:]]
        details.append("The game itself plays normally: the 2600 view (V) shows it as it is.")
    else:
        details = ["Its tables look like Adventure's, so it should work - if anything is drawn in the wrong "
                   "place, this is why."]
    details.append(f"(MD5 {digest}; the supported one is {SUPPORTED})")
    return headline, details
