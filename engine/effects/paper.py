"""The paper look's sound effects: a child's toy box - a little xylophone, a slide whistle, a kazoo for the
dragons - and the rustle of the sketchbook's paper.
"""

import numpy as np

from engine.chiptune import RATE
from engine.effects.tools import (GATE_CLOSE, GATE_OPEN, burble, clicks, cluck, decay, place, run, seconds,
                                  sine, soft_noise, sweep, times)
from engine.nature import fade_in_out


def xylophone(pitch, length):
    """A wooden bar struck: the note, and a quick high overtone that dies first."""
    bar = sine(pitch, length) * decay(length, 0.25)
    knock = sine(pitch * 4, length) * decay(length, 0.03) * 0.4
    return bar + knock


def squeaker(pitch, length):
    """A squeaky toy: a thin, bright whistle following a pitch (two octaves up from a real hen)."""
    return sine(pitch * 2, length) + 0.3 * sine(pitch * 4, length)


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


def growl_roar(voice):
    """A dragon roars - as a child would: a kazoo, rising and falling."""
    low, high = 180 * voice.pitch, 260 * voice.pitch
    rise = kazoo(low, high, 0.25 * voice.length)
    fall = kazoo(high, 150 * voice.pitch, 0.5 * voice.length)
    return place([(0, rise), (0.25 * voice.length, fall)], 0.8 * voice.length)


def eaten():
    """Swallowed: a slide whistle all the way down."""
    length = seconds(0.8)
    slide = sine(sweep(1400, 250, length), length) * np.minimum(1, (0.8 - times(length)) / 0.15)
    return slide


def growl_dies(voice):
    """The sword strikes home: a falling kazoo, and three bars going down."""
    sigh = kazoo(240 * voice.pitch, 110 * voice.pitch, 0.7 * voice.length)
    bars = run([67, 64, 60], 0.18, xylophone, ring=0.5)
    return place([(0, sigh), (0.7 * voice.length - 0.15, bars)], 0.9 + 0.7 * voice.length)


def roar(voice):
    """A dragon roars - or squawks, or gurgles, as its cast says (tools.Voice)."""
    if voice.kind == "squawk":
        return cluck(squeaker, voice)
    if voice.kind == "gurgle":
        return burble(lambda pitch, length: sine(pitch, length), voice)
    return growl_roar(voice)


def dragon_dies(voice):
    """The sword strikes home. A bird or a swamp thing gives one last, slow, sinking cry."""
    if voice.kind == "growl":
        return growl_dies(voice)
    last_cry = roar(voice._replace(pitch=voice.pitch * 0.75, length=voice.length * 1.5))
    return place([(0, last_cry), (len(last_cry) / RATE - 0.1, run([67, 64, 60], 0.18, xylophone, ring=0.5))],
                 len(last_cry) / RATE + 0.8)


def tick(index):
    """A toy ratchet's click: a tiny wooden tap."""
    length = seconds(0.03)
    return xylophone(1400 + 200 * (index % 2), length) * decay(length, 0.008)


def gate_open():
    """A wind-up toy's ratchet, quick, and a bar struck at the top."""
    bar = xylophone(784.0, seconds(0.5))
    return place([(0, clicks(tick, 0.035, GATE_OPEN - 0.1) * 0.6), (GATE_OPEN - 0.1, bar)], GATE_OPEN + 0.5)


def gate_close():
    """The ratchet clicking slowly down, and a low bar as the gate lands."""
    bar = xylophone(261.6, seconds(0.6))
    return place([(0, clicks(tick, 0.08, GATE_CLOSE - 0.1) * 0.6), (GATE_CLOSE - 0.1, bar)], GATE_CLOSE + 0.6)


def win():
    """Up the xylophone, and a chord held on it - a happy ending."""
    climb = run([60, 64, 67, 72, 76, 79], 0.08, xylophone, ring=0.6)
    chord = sum(xylophone(pitch, seconds(1.4)) for pitch in (523.3, 659.3, 784.0)) / 2
    return place([(0, climb), (0.5, chord)], 2.0)


EFFECTS = {"pickup": pickup, "drop": drop, "roar": roar, "eaten": eaten, "dragon_dies": dragon_dies,
           "win": win, "gate_open": gate_open, "gate_close": gate_close}
