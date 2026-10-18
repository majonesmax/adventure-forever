"""The paper look's sound effects: a child's toy box - a little xylophone, a slide whistle, a kazoo for the
dragons - and the rustle of the sketchbook's paper.
"""

import numpy as np

from engine.chiptune import RATE
from engine.effects.tools import decay, place, run, seconds, sine, soft_noise, sweep, times
from engine.nature import fade_in_out


def xylophone(pitch, length):
    """A wooden bar struck: the note, and a quick high overtone that dies first."""
    bar = sine(pitch, length) * decay(length, 0.25)
    knock = sine(pitch * 4, length) * decay(length, 0.03) * 0.4
    return bar + knock


def rustle(length_seconds, seed):
    """A page turning, quickly."""
    length = seconds(length_seconds)
    swell = np.sin(np.pi * np.linspace(0, 1, length)) ** 2
    return soft_noise(length, 1500, 6000, seed=seed) * swell


def kazoo(start_hz, end_hz, length_seconds):
    """A kazoo: a buzzy hum, sliding, with a voice's wobble."""
    length = seconds(length_seconds)
    pitch = sweep(start_hz, end_hz, length) * (1 + 0.02 * np.sin(2 * np.pi * 6 * times(length)))
    phase = np.cumsum(pitch) / RATE % 1.0
    buzz = 2 * phase - 1                                   # a sawtooth: every overtone, like a kazoo
    softened = np.convolve(buzz, np.ones(6) / 6, "same")   # a little less harsh
    return softened * fade_in_out(length, 0.05, 0.1)


def pickup():
    """Two bars, up a fifth, and the paper rustles."""
    return place([(0, run([72, 79], 0.08, xylophone, ring=0.5)), (0, rustle(0.15, seed=1) * 0.2)], 0.7)


def drop():
    """A low bar, softly."""
    return run([60], 0.0, xylophone, ring=0.4) * 0.8


def roar():
    """A dragon roars - as a child would: a kazoo, rising and falling."""
    rise = kazoo(180, 260, 0.25)
    fall = kazoo(260, 150, 0.5)
    return place([(0, rise), (0.25, fall)], 0.8)


def eaten():
    """Swallowed: a slide whistle all the way down."""
    length = seconds(0.8)
    slide = sine(sweep(1400, 250, length), length) * np.minimum(1, (0.8 - times(length)) / 0.15)
    return slide


def dragon_dies():
    """The sword strikes home: a falling kazoo, and three bars going down."""
    sigh = kazoo(240, 110, 0.7)
    bars = run([67, 64, 60], 0.18, xylophone, ring=0.5)
    return place([(0, sigh), (0.55, bars)], 1.6)


def win():
    """Up the xylophone, and a chord held on it - a happy ending."""
    climb = run([60, 64, 67, 72, 76, 79], 0.08, xylophone, ring=0.6)
    chord = sum(xylophone(pitch, seconds(1.4)) for pitch in (523.3, 659.3, 784.0)) / 2
    return place([(0, climb), (0.5, chord)], 2.0)


EFFECTS = {"pickup": pickup, "drop": drop, "roar": roar, "eaten": eaten, "dragon_dies": dragon_dies,
           "win": win}
