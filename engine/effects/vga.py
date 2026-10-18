"""The VGA look's sound effects: an early-90s PC sound card's FM chip - two-operator tones, bright and a
little buzzy, with no echo (engine/fm.py's voice, played harder).
"""

import numpy as np

from engine.chiptune import RATE, midi_hz
from engine.effects.tools import chip_noise, decay, place, run, seconds, sweep, times
from engine.fm import env, fm


def beep(pitch, length):
    """The FM chip's plain tone: bright at the start, mellowing."""
    return fm(pitch, length, ratio=2.0, index=2.5, index_decay=0.08) * env(length, decay=0.12, sustain=0.3)


def gliding(start_hz, end_hz, length_seconds, ratio, index):
    """An FM tone gliding in pitch (fm() holds one pitch, so the phase is built here)."""
    length = seconds(length_seconds)
    pitch = sweep(start_hz, end_hz, length)
    phase = 2 * np.pi * np.cumsum(pitch) / RATE
    return np.sin(phase + index * np.sin(phase * ratio))


def pickup():
    """Two quick beeps, up an octave."""
    return run([76, 88], 0.07, beep, ring=0.12)


def drop():
    """A short beep dropping."""
    sound = gliding(330, 150, 0.12, ratio=1.0, index=1.5)
    return sound * decay(len(sound), 0.05)


def roar():
    """A dragon roars: a growling FM tone with a deep wobble."""
    sound = gliding(150, 70, 0.7, ratio=0.5, index=5.0)
    wobble = 1 + 0.25 * np.sin(2 * np.pi * 18 * times(len(sound)))
    return sound * wobble * env(len(sound), attack=0.02, decay=0.4, sustain=0.5, release=0.1) * 0.8


def eaten():
    """Swallowed: a long fall in pitch, and a crunch."""
    fall = gliding(900, 80, 0.6, ratio=1.0, index=2.0)
    fall = fall * env(len(fall), decay=0.4, sustain=0.4, release=0.1)
    crunch_length = seconds(0.2)
    crunch = chip_noise(crunch_length, pitch=0.3, seed=4) * decay(crunch_length, 0.06)
    return place([(0, fall * 0.7), (0.55, crunch)], 0.8)


def dragon_dies():
    """The sword strikes home: a noisy blast and a falling, buzzing tone."""
    blast_length = seconds(0.3)
    blast = chip_noise(blast_length, pitch=0.3, seed=5) * decay(blast_length, 0.1)
    fall = gliding(500, 40, 0.9, ratio=1.5, index=3.0)
    fall = fall * env(len(fall), decay=0.5, sustain=0.3, release=0.15)
    return place([(0, blast * 0.8), (0.05, fall * 0.7)], 1.0)


def win():
    """A brassy fanfare."""
    def brass(pitch, length):
        return fm(pitch, length, ratio=1.0, index=3.0, index_decay=0.3) * env(length, attack=0.02, decay=0.4,
                                                                               sustain=0.5, release=0.05)
    fanfare = run([67, 67, 67, 72], 0.12, brass, ring=0.11)
    held_length = seconds(0.9)
    held = sum(brass(midi_hz(midi), held_length) for midi in (72, 76, 79)) / 3
    return place([(0, fanfare), (0.48, held)], 1.4)


EFFECTS = {"pickup": pickup, "drop": drop, "roar": roar, "eaten": eaten, "dragon_dies": dragon_dies,
           "win": win}
