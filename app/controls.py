"""Every key the game answers to - the ONE list. The help panel (H) draws it; README.md's "Controls" table and
the downloads' package/README.txt list the same keys, and tests/test_controls.py fails if any key the window
handles (app/window.py: JOYSTICK, KEYS, SHIFTED) is missing from this list or from either README.

    SECTIONS   [(title, [(keys, what, [pygame key names it covers])])]
"""

SECTIONS = [
    ("PLAY", [
        ("Arrows", "move", ["up", "down", "left", "right"]),
        ("Space", "fire: drop what you carry", ["space"]),
        ("Tab", "game select (games 1-3)", ["tab"]),
        ("Enter", "game reset: start", ["return"]),
    ]),
    ("WHAT YOU SEE", [
        ("L", "next look: NES, SNES", ["l"]),
        ("C", "next cast: the knight, PBJ and friends", ["c"]),
        ("W", "next world: castles, kingdoms", ["w"]),
        ("I", "which look, cast and world", ["i"]),
        ("V", "view: side by side, look, 2600, grid", ["v"]),
        ("Shift+L/C/W", "the grid's comparison: its own", ["shift+l", "shift+c", "shift+w"]),
        ("F", "fullscreen on / off", ["f"]),
        ("T", "room scrolls on / off", ["t"]),
    ]),
    ("SOUND", [
        ("M", "music on / off", ["m"]),
        ("- / =", "music quieter / louder", ["-", "="]),
        ("N", "next music source", ["n"]),
    ]),
    ("MORE", [
        ("S", "screenshot", ["s"]),
        ("R", "record on / off (needs ffmpeg)", ["r"]),
        ("D", "debug line: speed, room, render time", ["d"]),
        ("P", "pause", ["p"]),
        ("H", "help: every key", ["h"]),
        ("Esc", "quit", ["escape"]),
    ]),
]


def covered():
    """Every key name the list covers (pygame.key.name style; "shift+l" for Shift+L)."""
    return {name for _, rows in SECTIONS for _, _, names in rows for name in names}


def labels():
    return [keys for _, rows in SECTIONS for keys, _, _ in rows]
