"""What the looks' sound effects are made with: pitch sweeps, decays, NES-style and smooth noise, an echo, and
a way to lay sounds out along a track. Every effect is a mono float track; engine/effects/__init__.py sets
its loudness.
"""

from collections import namedtuple

import numpy as np

from engine.chiptune import RATE, midi_hz


Voice = namedtuple("Voice", "pitch length")   # a dragon's: x its pitch, x how long it roars
DRAGON_VOICES = {"red": Voice(1.35, 0.75),      # Rhindle, the fastest and fiercest: high and quick
                 "yellow": Voice(1.0, 1.0),     # Yorgle
                 "green": Voice(0.7, 1.3)}      # Grundle: deep and slow
GATE_OPEN, GATE_CLOSE = 0.5, 1.3                # seconds: the portcullis flies up, and comes down slowly


def seconds(count):
    return int(count * RATE)


def times(length):
    """Each sample's time in seconds."""
    return np.arange(length) / RATE


def sweep(start_hz, end_hz, length):
    """A pitch gliding from start_hz to end_hz (evenly in pitch, not in Hz)."""
    return start_hz * (end_hz / start_hz) ** np.linspace(0, 1, length)


def decay(length, time_constant):
    return np.exp(-times(length) / time_constant)


def sine(pitch, length):
    """A sine following a pitch that may change from sample to sample."""
    pitch = np.broadcast_to(pitch, (length,))
    return np.sin(2 * np.pi * np.cumsum(pitch) / RATE)


def chip_noise(length, pitch=1.0, seed=1):
    """NES-style noise: a random level held for 1/pitch of the time - lower pitch, lower rumble."""
    rng = np.random.default_rng(seed)
    hold = max(1, int(round(1 / pitch)))
    levels = rng.choice([-1.0, 1.0], length // hold + 1)
    return np.repeat(levels, hold)[:length]


def soft_noise(length, low_hz, high_hz, seed=1):
    """Noise with only the frequencies from low_hz to high_hz: a breath, a rustle, a rumble. Peak about 1."""
    signal = np.random.default_rng(seed).normal(size=length)
    frequencies = np.fft.rfftfreq(length, 1 / RATE)
    keep = (frequencies >= low_hz) & (frequencies <= high_hz)
    out = np.fft.irfft(np.fft.rfft(signal) * keep, length)
    return out / max(1e-9, np.abs(out).max())


def place(parts, total):
    """[(start in seconds, samples), ...] -> one track of `total` seconds."""
    track = np.zeros(seconds(total))
    for start, samples in parts:
        begin = seconds(start)
        end = min(len(track), begin + len(samples))
        track[begin:end] += samples[:end - begin]
    return track


def run(midis, gap, voice, ring=0.3):
    """Notes one after another, `gap` seconds apart, each ringing `ring` seconds: voice(pitch, length)."""
    parts = [(index * gap, voice(midi_hz(midi), seconds(ring))) for index, midi in enumerate(midis)]
    return place(parts, gap * len(midis) + ring)


def echo(track, delay=0.18, feedback=0.4, repeats=4):
    """Repeats of the sound, each quieter - a room's (or a SNES's) echo. The track grows to hold them."""
    step = seconds(delay)
    out = np.concatenate([track, np.zeros(step * repeats)])
    for repeat in range(1, repeats + 1):
        out[step * repeat:step * repeat + len(track)] += track * feedback ** repeat
    return out


def clicks(click, every, length_seconds, getting=1.0):
    """A ratchet or a chain: `click()` (a short sound) every `every` seconds, each `getting` x as loud as
    the one before."""
    count = int(length_seconds / every)
    parts = [(index * every, click(index) * getting ** index) for index in range(count)]
    return place(parts, length_seconds + 0.2)
