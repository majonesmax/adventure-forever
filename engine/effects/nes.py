"""The NES look's sound effects: the game's six sounds on the NES's own voices - two pulse waves, a stepped
triangle and noise (engine/chiptune.py, the same as the music).
"""

from engine.chiptune import envelope, midi_hz, pulse, triangle
from engine.effects.tools import chip_noise, decay, place, run, seconds, sweep


def blip(pitch, length):
    return pulse(pitch, length, 0.25) * envelope(length, decay=0.05, sustain=0.3)


def pickup():
    """A quick rising arpeggio."""
    return run([72, 76, 79, 84], 0.045, blip, ring=0.08)


def drop():
    """A soft thump, falling."""
    length = seconds(0.14)
    return triangle(sweep(320, 110, length), length) * decay(length, 0.05)


def roar():
    """A dragon roars: a thin, growling pulse sliding down over a rumble."""
    length = seconds(0.6)
    growl = pulse(sweep(240, 100, length), length, 0.125, vibrato=0.06)
    rumble = chip_noise(length, pitch=0.08, seed=1)
    loudness = envelope(length, attack=0.03, decay=0.35, sustain=0.4)
    return (0.7 * growl + 0.25 * rumble) * loudness


def eaten():
    """Swallowed: a run falling away, then a crunch."""
    fall = run(list(range(76, 50, -3)), 0.05, lambda pitch, length: pulse(pitch, length, 0.5) *
               envelope(length, decay=0.04, sustain=0.2), ring=0.07)
    crunch_length = seconds(0.25)
    crunch = chip_noise(crunch_length, pitch=0.25, seed=2) * decay(crunch_length, 0.07)
    return place([(0, fall * 0.7), (0.45, crunch)], 0.8)


def dragon_dies():
    """The sword strikes home: a burst of noise, and a long falling tone."""
    burst_length = seconds(0.2)
    burst = chip_noise(burst_length, pitch=0.5, seed=3) * decay(burst_length, 0.06)
    fall_length = seconds(0.8)
    fall = triangle(sweep(420, 55, fall_length), fall_length) * envelope(fall_length, decay=0.5, sustain=0.2)
    return place([(0, burst), (0.05, fall)], 0.9)


def win():
    """A fanfare: the run up, and a ringing chord."""
    fanfare = run([67, 72, 76, 79], 0.09, blip, ring=0.12)
    chord_length = seconds(1.0)
    chord = sum(pulse(midi_hz(midi), chord_length, 0.25) for midi in (79, 84, 88)) / 3
    return place([(0, fanfare), (0.36, chord * envelope(chord_length, decay=0.4, sustain=0.25))], 1.4)


EFFECTS = {"pickup": pickup, "drop": drop, "roar": roar, "eaten": eaten, "dragon_dies": dragon_dies,
           "win": win}
