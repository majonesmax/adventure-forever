"""The SNES look's sound effects: soft, rounded voices - bells, an electric piano, a breathy growl - with the
echo the Super NES's sound chip put on nearly everything.
"""

import numpy as np

from engine.chiptune import RATE
from engine.effects.tools import decay, echo, place, run, seconds, sine, soft_noise, sweep, times
from engine.fm import bell, env, epiano


def pickup():
    """A bright little bell run, rising."""
    return echo(run([79, 83, 86, 91], 0.06, bell, ring=0.5) * 0.8)


def drop():
    """Set down on the grass: a soft, low knock."""
    length = seconds(0.2)
    knock = sine(sweep(200, 110, length), length) * decay(length, 0.05)
    tap = soft_noise(length, 300, 2000, seed=1) * decay(length, 0.008) * 0.3
    return echo(knock + tap, feedback=0.25, repeats=2)


def growl(start_hz, end_hz, length_seconds, seed):
    """A big animal's voice: a low, rough tone sliding from start_hz to end_hz, with breath in it."""
    length = seconds(length_seconds)
    pitch = sweep(start_hz, end_hz, length) * (1 + 0.03 * np.sin(2 * np.pi * 7 * times(length)))
    phase = 2 * np.pi * np.cumsum(pitch) / RATE
    rough = np.sin(phase + 2.5 * np.sin(phase / 2))   # a modulator an octave down: a rasp under the tone
    breath = soft_noise(length, 150, 1400, seed=seed)
    return (0.8 * rough + 0.2 * breath) * env(length, attack=0.08, decay=0.5, sustain=0.5, release=0.2)


def roar():
    """A dragon roars."""
    return echo(growl(150, 85, 0.9, seed=2), feedback=0.3)


def eaten():
    """Swallowed: a deep gulp, then a falling minor run on the piano."""
    gulp_length = seconds(0.3)
    gulp = sine(sweep(160, 60, gulp_length), gulp_length) * decay(gulp_length, 0.12)
    fall = run([64, 60, 57, 52, 48], 0.11, epiano, ring=0.6)
    return echo(place([(0, gulp), (0.25, fall * 0.7)], 1.4))


def dragon_dies():
    """The sword strikes home: a growl falling away under a low, dark bell."""
    voice = growl(170, 55, 1.1, seed=3)
    toll_length = seconds(1.5)
    toll = bell(110.0, toll_length) * 0.5
    return echo(place([(0, voice), (0.15, toll)], 1.7), feedback=0.35)


def win():
    """A run up the piano into a ringing bell chord."""
    climb = run([60, 64, 67, 72, 76], 0.08, epiano, ring=0.5)
    chord_length = seconds(1.6)
    chord = sum(bell(pitch, chord_length) for pitch in (523.3, 659.3, 784.0)) / 3
    return echo(place([(0, climb), (0.42, chord)], 2.0))


EFFECTS = {"pickup": pickup, "drop": drop, "roar": roar, "eaten": eaten, "dragon_dies": dragon_dies,
           "win": win}
