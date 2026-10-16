"""The pbj world: candy, ice and fire kingdoms, meadows, a dark forest, crypts and crystal caves - painted
rather than tiled (scenery.py): rounded walls with a front face, battlements with caps, scattered flowers
and pebbles. Each place's theme is set in pack.json ("areas": {place: {"theme": ...}}).
"""

import functools
import os

import numpy as np

import scenery as SC
from content import pictures as PIC
from content.world import World, area

GRASS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grass.png")
GATE_THEME = {"gold": "candy", "white": "ice", "black": "fire"}


@functools.cache
def grass_tile():
    return PIC.load(GRASS)[..., :3]


class CustomWorld(World):
    def theme(self, room_num):
        return self.setting(area(room_num), "theme") or "grass"

    def room(self, room):
        n = room["room"]
        if n not in self.rooms:
            t = self.theme(n)
            grass = grass_tile() if t in ("grass", "candy") else None
            self.rooms[n] = SC.paint_room(room, t, floor_tile=grass, seed=n)
        return self.rooms[n]

    def colour(self, room_num):
        return SC.THEMES[self.theme(room_num)]["title"]

    def gate(self, castle, w, h):
        return SC.gate_sprite(w, h, GATE_THEME[castle]) if h > 0 else None

    def wall_tile(self, room_num):
        return None
