"""The NES look's sound effects: the game's six sounds on the NES's own voices - two pulse waves, a stepped
triangle and noise (engine/chiptune.py, the same as the music).
"""

from engine.chiptune import RATE, envelope, midi_hz, pulse, triangle
from engine.effects.tools import (GATE_CLOSE, GATE_OPEN, burble, chip_noise, clicks, cluck, decay, place, run,
                                  seconds, sweep)


def chip_tone(pitch, length):
    """A pulse wave following a pitch (the squawks' and gurgles' voice)."""
    return pulse(pitch, length, 0.25)


def blip(pitch, length):
    return pulse(pitch, length, 0.25) * envelope(length, decay=0.05, sustain=0.3)


def pickup():
    """A quick rising arpeggio."""
    return run([72, 76, 79, 84], 0.045, blip, ring=0.08)


def drop():
    """A soft thump, falling."""
    length = seconds(0.14)
    return triangle(sweep(320, 110, length), length) * decay(length, 0.05)


def growl_roar(voice):
    """A dragon roars: a thin, growling pulse sliding down over a rumble."""
    length = seconds(0.6 * voice.length)
    growl = pulse(sweep(240 * voice.pitch, 100 * voice.pitch, length), length, 0.125, vibrato=0.06)
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


def growl_dies(voice):
    """The sword strikes home: a burst of noise, and a long falling tone."""
    burst_length = seconds(0.2)
    burst = chip_noise(burst_length, pitch=0.5, seed=3) * decay(burst_length, 0.06)
    fall_length = seconds(0.8 * voice.length)
    fall = triangle(sweep(420 * voice.pitch, 55, fall_length), fall_length)
    fall = fall * envelope(fall_length, decay=0.5, sustain=0.2)
    return place([(0, burst), (0.05, fall)], 0.1 + 0.8 * voice.length)


def roar(voice):
    """A dragon roars - or squawks, or gurgles, as its cast says (tools.Voice)."""
    if voice.kind == "squawk":
        return cluck(chip_tone, voice)
    if voice.kind == "gurgle":
        bubbles = burble(chip_tone, voice)
        return bubbles + 0.06 * chip_noise(len(bubbles), pitch=0.05, seed=7)
    return growl_roar(voice)


def dragon_dies(voice):
    """The sword strikes home. A bird or a swamp thing gives one last, slow, sinking cry."""
    if voice.kind == "growl":
        return growl_dies(voice)
    last_cry = roar(voice._replace(pitch=voice.pitch * 0.75, length=voice.length * 1.5))
    burst = chip_noise(seconds(0.2), pitch=0.5, seed=3) * decay(seconds(0.2), 0.06)
    return place([(0, burst), (0.1, last_cry)], 0.1 + len(last_cry) / RATE)


def link(index):
    """One link of the portcullis chain: a short metallic tick."""
    length = seconds(0.02)
    return chip_noise(length, pitch=0.7, seed=10 + index % 4) * decay(length, 0.005)


def clank():
    """The portcullis reaching the end: a heavy clank."""
    length = seconds(0.25)
    return (chip_noise(length, pitch=0.2, seed=5) * 0.6 + triangle(110, length)) * decay(length, 0.07)


def gate_open():
    """The chain rattling fast as the gate flies up, and a clank."""
    rattle = clicks(link, 0.03, GATE_OPEN - 0.1) * 0.6
    return place([(0, rattle), (GATE_OPEN - 0.1, clank())], GATE_OPEN + 0.3)


def gate_close():
    """The chain paying out slowly as the gate comes down, and a clank as it lands."""
    rattle = clicks(link, 0.07, GATE_CLOSE - 0.1) * 0.6
    return place([(0, rattle), (GATE_CLOSE - 0.1, clank())], GATE_CLOSE + 0.3)


def win():
    """A fanfare: the run up, and a ringing chord."""
    fanfare = run([67, 72, 76, 79], 0.09, blip, ring=0.12)
    chord_length = seconds(1.0)
    chord = sum(pulse(midi_hz(midi), chord_length, 0.25) for midi in (79, 84, 88)) / 3
    return place([(0, fanfare), (0.36, chord * envelope(chord_length, decay=0.4, sustain=0.25))], 1.4)


EFFECTS = {"pickup": pickup, "drop": drop, "roar": roar, "eaten": eaten, "dragon_dies": dragon_dies,
           "win": win, "gate_open": gate_open, "gate_close": gate_close}
