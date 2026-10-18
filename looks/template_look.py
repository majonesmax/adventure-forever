"""TEMPLATE LOOK - the smallest complete look (platform). Copy this file to start a new one: an Amiga look, a
C64 look, a Game Boy look...

Run it:   python play.py --look template                          (its own cast and world)
          python play.py --look template --cast pbj --world pbj   (any cast, any world)
(It isn't in the L cycle - add your own look to LOOKS in looks/__init__.py to put it there.)

How a look fits in:

    emulator (engine/emulator.py)  runs the real 2600 game
         |  128 bytes of RAM every frame
    GameState (engine/state.py)    room, hero, objects, carried item, won... - named, no RAM addresses
         |
    YOUR LOOK                      GameState -> a 256x240 picture, showing
       + a world (content/)          where: each room's walls and floor, the gates, the places' names
       + a cast (content/)           who: the hero, dragons, items, the win message
         |
    the window (play.py, app/)     shows it, scrolls between rooms, records, puts it in the grid

This template inherits RoomLook (looks/base.py), which already draws the world's rooms and places the cast
where the game has it - the hero's walk cycle, the held item, torch light in dark rooms, the win sequence.
So a look is the console: its rules for pictures (adapt, adapt_scenery) and its screens (the status bar,
the title, the win).
"""

import numpy as np

from looks.base import RoomLook
from shared import hud as HUD
from shared import layout as L

BAR, TEXT, GOLD = (0, 0, 0), (232, 232, 240), (240, 200, 80)


class TemplateLook(RoomLook):
    platform = "template"            # play.py --look template
    platform_name = "TEMPLATE LOOK"  # the label over this look's pane in the grid view
    own_pack = "template"            # whose cast and world it shows unless others are chosen

    def adapt(self, sprite):
        """This console's rules for the cast's pictures - called once per picture. A real look enforces its
        hardware here (the NES look snaps colours to the NES palette). This one shows them as they are."""
        return sprite

    def adapt_scenery(self, picture):
        """The same for the world's rooms and gates."""
        return picture

    def draw_hud(self, screen, state, frame_no):
        """The status bar above the room: the look's name and which game (1-3) is being played."""
        screen[:L.HUD_H] = BAR
        HUD.draw_text(screen, "TEMPLATE LOOK", 8, 12, TEXT)
        HUD.draw_text(screen, f"GAME {state.game}", 8, 28, TEXT)

    def title_screen(self, state, frame_no):
        """The game-select screen (before Enter is pressed). Return a whole new screen."""
        screen = np.zeros((L.SCREEN_H, L.SCREEN_W, 3), np.uint8)
        HUD.draw_text(screen, "ADVENTURE", 92, 100, TEXT)
        HUD.draw_text(screen, f"GAME {state.game} - PRESS ENTER", 52, 130, TEXT)
        return screen

    def win_banner(self, screen, state, frame_no):
        """Painted over the room once the chalice is home - with the cast's first line ("YOU WIN!")."""
        text = self.cast.win_lines[0]
        HUD.draw_text(screen, text, (L.SCREEN_W - HUD.text_width(text)) // 2, 120, GOLD)
