"""The characters heard moving, while the music is off: the hero's footsteps (on grass, stone or snow - the
ground of the place, from its ambience), a dragon's heavy stomps, the bat's wings. Only what's in the hero's
room, each heard from where it is, left or right. engine/nature.py makes the sounds; engine/ambience.py plays
them with the rest of the world's sounds.
"""

import threading

import numpy as np

from engine import nature as N
from engine.ambience import call_samples

DRAGONS, BAT = (0x06, 0x07, 0x08), 0x0E      # object numbers (engine/objects.py)
GROUND = {"summer": "grass", "woods": "grass", "frost": "snow"}   # an ambience -> its ground; else stone
STEP_EVERY = {"hero": 14, "dragon": 20, "bat": 8}        # frames of moving between one sound and the next
LOUDNESS = {"hero": 0.55, "dragon": 1.1, "bat": 0.4}     # x the ambience's CALL_LEVEL
STOPPED = 8                                  # frames without moving that make a stop
VARIANTS = 6
ROOM_MIDDLE, HALF_WIDTH = 80, 100            # the game's x across a room -> left and right
WIDEST = 0.7


def pan(x):
    return float(np.clip((x - ROOM_MIDDLE) / HALF_WIDTH, -WIDEST, WIDEST))


class Footsteps:
    """follow() once a frame while the ambience plays. The sounds are made in the background at the start."""

    def __init__(self, ambience):
        self.ambience = ambience
        self.sounds = {}
        self.last_seen, self.moving_for, self.still_for = {}, {}, {}
        self.rng = np.random.default_rng()
        threading.Thread(target=self.make_all, daemon=True).start()

    def make_all(self):
        def made(make, who):
            return [call_samples(make(seed), LOUDNESS[who]) for seed in range(VARIANTS)]
        for ground in ("grass", "stone", "snow"):
            self.sounds[ground] = made(lambda seed, ground=ground: N.step(ground, seed), "hero")
        self.sounds["dragon"] = made(N.stomp, "dragon")
        self.sounds["bat"] = made(N.wingbeat, "bat")

    def follow(self, state, ambience_name):
        """Who moved since the last frame, and a sound for each who's moved long enough."""
        if state.on_title_screen or ambience_name is None:
            self.last_seen = {}
            return
        movers = {"hero": ("hero", state.hero)}
        for number, x, y, _state in state.objects:
            if number == state.carried:
                continue
            if number in DRAGONS:
                movers[number] = ("dragon", (x, y))
            elif number == BAT:
                movers[number] = ("bat", (x, y))
        for key, (who, place) in movers.items():
            self.watch(key, who, place, GROUND.get(ambience_name, "stone"))
        self.last_seen = {key: place for key, (_who, place) in movers.items()}

    def watch(self, key, who, place, ground):
        """Count the frames someone's been on the move (the game moves them only every few frames, so a
        short stop doesn't count) and make a sound every STEP_EVERY of them."""
        moved = self.last_seen.get(key, place) != place
        self.still_for[key] = 0 if moved else self.still_for.get(key, STOPPED) + 1
        if self.still_for[key] > STOPPED:
            self.moving_for[key] = 0
            return
        self.moving_for[key] = self.moving_for.get(key, 0) + 1
        if self.moving_for[key] % STEP_EVERY[who] == 1:
            choices = self.sounds.get(ground if who == "hero" else who)
            if choices:
                self.ambience.add(choices[self.rng.integers(len(choices))], pan(place[0]))
