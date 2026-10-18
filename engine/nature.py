"""The world's own sounds, for a bright summer day: a breeze, leaves, birds of a few kinds, a woodpecker, a
bee going by; and for indoors and underground, still air, drips, a fire's crackle. engine/ambience.py plays
them. (Made the way Haunted House remastered makes its house's sounds: shaped noise and whistles.)

Noise is shaped in the frequency domain, so a loop of it joins up without a seam. Nothing bright is ever
steady - a steady hiss sounds like static - so the leaves only rustle when the breeze gusts. Each side gets
its own noise, so the air is wide; the calls are mono, and placed left or right as they play.
"""

import numpy as np

from engine.chiptune import RATE

LOOP_SECONDS = 16       # a bed's length; it loops
RUSTLE_FROM = 0.5       # the leaves rustle only when the breeze is stronger than this (0-1)


def seconds(count):
    return int(count * RATE)


def decay(length, time_constant):
    return np.exp(-np.arange(length) / RATE / time_constant)


def fade_in_out(length, rise, fall):
    """An envelope rising over `rise` seconds and falling over the last `fall`."""
    time = np.arange(length) / RATE
    return np.minimum(1, time / rise) * np.minimum(1, (length / RATE - time) / fall).clip(0, 1)


def filtered(signal, low_hz, high_hz, tilt=0.0):
    """Only the frequencies from low_hz to high_hz of each column, louder low down by `tilt` (0 flat, 1 a
    deep rumble); circular, so a loop stays a loop. Peak about 1."""
    length = len(signal)
    frequencies = np.fft.rfftfreq(length, 1 / RATE)
    keep = (frequencies >= low_hz) & (frequencies <= high_hz)
    shape = keep / np.maximum(frequencies, max(low_hz, 1e-3)) ** tilt
    out = np.fft.irfft(np.fft.rfft(signal, axis=0) * shape[:, None], length, axis=0)
    return out / max(1e-9, np.abs(out).max())


def band(signal, centre_hz, octaves):
    """The frequencies around centre_hz, falling away smoothly on both sides (`octaves` wide at half
    strength) - softer than filtered()'s hard edges, which make noise sound like a radio between stations.
    Circular, like filtered(). Peak about 1."""
    length = len(signal)
    frequencies = np.maximum(np.fft.rfftfreq(length, 1 / RATE), 1.0)
    distance = np.log2(frequencies / centre_hz) / (octaves / 2)
    shape = 0.5 ** (distance ** 2)
    out = np.fft.irfft(np.fft.rfft(signal, axis=0) * shape[:, None], length, axis=0)
    return out / max(1e-9, np.abs(out).max())


def noise(length, seed):
    return np.random.default_rng(seed).normal(size=(length, 2))


def whistle(pitch):
    """A pure tone following a pitch that may change from sample to sample."""
    return np.sin(2 * np.pi * np.cumsum(pitch) / RATE)


# --- beds: loops ----------------------------------------------------------------------------------------
def gusts(seed, calm=0.3):
    """How hard the breeze blows through the loop, 0-1: slow, uneven swells (a few each loop), never quite
    still - `calm` at the quietest."""
    length = seconds(LOOP_SECONDS)
    slow = filtered(noise(length, seed)[:, :1], 0.05, 0.35)[:, 0]
    return calm + (1 - calm) * ((slow + 1) / 2) ** 1.5


def breeze(seed, calm=0.3):
    """Air moving over open ground: a soft, low rush that rises and falls with the gusts."""
    length = seconds(LOOP_SECONDS)
    body = band(noise(length, seed), 220, 2.5)
    return body * gusts(seed + 1, calm)[:, None]


def leaves(seed):
    """Leaves stirring: a light, uneven rustle, only in the strongest gusts (the same gusts as
    breeze(seed - 1)) - and silent in between, so it never settles into a hiss."""
    length = seconds(LOOP_SECONDS)
    rustle = band(noise(length, seed), 2200, 2.0)
    flutter = np.abs(filtered(noise(length, seed + 1), 4, 18))
    strongest = np.clip((gusts(seed, calm=0.0) - RUSTLE_FROM) / (1 - RUSTLE_FROM), 0, 1) ** 2
    return rustle * flutter * strongest[:, None]


def still_air(seed, low_hz=80, high_hz=400):
    """A room's or a cave's quiet: very low, barely moving air."""
    length = seconds(LOOP_SECONDS)
    return filtered(noise(length, seed), low_hz, high_hz, tilt=0.7) * gusts(seed + 1, calm=0.6)[:, None]


def embers(seed):
    """A fire burning low: a soft roar, with crackles here and there."""
    length = seconds(LOOP_SECONDS)
    rng = np.random.default_rng(seed)
    roar = filtered(noise(length, seed), 50, 350, tilt=0.6) * gusts(seed + 1, calm=0.5)[:, None]
    sparks = np.zeros((length, 2))
    count = 14 * LOOP_SECONDS
    for side in range(2):
        sparks[rng.integers(0, length, count), side] = rng.uniform(0.1, 1, count) ** 4
    crackle = filtered(sparks, 900, 4500)
    return roar + 0.8 * crackle


# --- calls: one-offs (mono) -----------------------------------------------------------------------------
def chirps(seed):
    """A small bird: a phrase of quick chirps, each a whistle that swoops and trills."""
    rng = np.random.default_rng(seed)
    phrase = np.zeros(seconds(1.6))
    start = 0.0
    for _chirp in range(rng.integers(3, 7)):
        length = seconds(rng.uniform(0.05, 0.13))
        time = np.arange(length) / RATE
        swoop = np.linspace(rng.uniform(2500, 4200), rng.uniform(2800, 5000), length)
        trill = 1 + 0.06 * np.sin(2 * np.pi * rng.uniform(25, 45) * time)
        chirp = whistle(swoop * trill) * np.sin(np.pi * time / time[-1]) ** 2
        begin = seconds(start)
        phrase[begin:begin + length] += chirp[:len(phrase) - begin]
        start += rng.uniform(0.09, 0.22)
    return phrase


def two_notes(seed):
    """A clear two-note whistle, high then lower - "fee-bee" - sometimes sung twice."""
    rng = np.random.default_rng(seed)
    high = rng.uniform(2900, 3600)
    notes = [(high, 0.32), (high * rng.uniform(0.8, 0.88), 0.38)] * rng.integers(1, 3)
    call = np.zeros(seconds(sum(length + 0.12 for _hz, length in notes) + 0.4))
    start = 0.0
    for pitch, length in notes:
        count = seconds(length)
        glide = pitch * np.linspace(1.02, 0.98, count)
        note = whistle(glide) * fade_in_out(count, 0.03, 0.12)
        begin = seconds(start)
        call[begin:begin + count] += note
        start += length + 0.12
        if pitch != high:
            start += 0.35   # a breath before it sings again
    return call


def trill(seed):
    """A warbler's run: a quick string of bright notes, falling, faster at the end."""
    rng = np.random.default_rng(seed)
    count_notes = rng.integers(12, 20)
    pitches = np.linspace(rng.uniform(4400, 5200), rng.uniform(2800, 3400), count_notes)
    lengths = np.linspace(0.07, 0.04, count_notes)
    call = np.zeros(seconds(lengths.sum() + 0.2))
    start = 0.0
    for pitch, length in zip(pitches, lengths):
        count = seconds(length * 0.8)
        note = whistle(np.full(count, pitch) * np.linspace(1.05, 0.97, count))
        begin = seconds(start)
        call[begin:begin + count] += note * np.sin(np.pi * np.linspace(0, 1, count)) ** 2
        start += length
    return call


def coo(seed):
    """A dove a way off: soft, low, breathy notes - coo-OO-oo, oo, oo."""
    rng = np.random.default_rng(seed)
    pitch = rng.uniform(440, 520)
    notes = [(1.0, 0.25, 0.1), (1.12, 0.5, 0.15), (0.95, 0.3, 0.45), (0.95, 0.35, 0.3), (0.95, 0.35, 0.0)]
    call = np.zeros(seconds(sum(length + gap for _step, length, gap in notes)))
    start = 0.0
    for step, length, gap in notes:
        count = seconds(length)
        time = np.arange(count) / RATE
        tone = whistle(pitch * step * (1 + 0.01 * np.sin(2 * np.pi * 6 * time)))
        breath = filtered(noise(count, seed)[:, :1], 300, 1500)[:, 0] * 0.25
        begin = seconds(start)
        call[begin:begin + count] += (tone + breath) * fade_in_out(count, 0.08, 0.15)
        start += length + gap
    return call


def woodpecker(seed):
    """A woodpecker drumming on a tree somewhere: a fast roll of knocks, dying away."""
    rng = np.random.default_rng(seed)
    pitch, knocks = rng.uniform(800, 1100), rng.integers(12, 20)
    gap = 1 / rng.uniform(14, 18)
    roll = np.zeros(seconds(knocks * gap + 0.1))
    for number in range(knocks):
        count = seconds(0.03)
        knock = np.sin(2 * np.pi * pitch * np.arange(count) / RATE) * decay(count, 0.006)
        clack = filtered(noise(count, seed + number)[:, :1], 1500, 4000)[:, 0] * decay(count, 0.002)
        begin = seconds(number * gap)
        roll[begin:begin + count] += (knock + 0.5 * clack) * 0.93 ** number
    return roll


def bee(seed):
    """A bee going by: a soft buzz that comes, passes and goes (engine/ambience.py moves it across)."""
    rng = np.random.default_rng(seed)
    count = seconds(rng.uniform(2.0, 3.0))
    time = np.arange(count) / RATE
    pitch = rng.uniform(190, 230) * (1 + 0.03 * np.sin(2 * np.pi * rng.uniform(3, 6) * time))
    phase = 2 * np.pi * np.cumsum(pitch) / RATE
    buzz = sum(np.sin(phase * harmonic) / harmonic for harmonic in range(1, 8))
    passing = np.sin(np.pi * time / time[-1]) ** 2
    return buzz * passing


def drip(seed):
    """A drop into a pool: a short plink that bends up."""
    rng = np.random.default_rng(seed)
    count = seconds(0.12)
    pitch = rng.uniform(900, 1600) * (1 + 0.6 * np.linspace(0, 1, count))
    return whistle(pitch) * decay(count, 0.025)


def pop(seed):
    """A log settling in the fire: a sharp little crack."""
    count = seconds(0.06)
    return filtered(noise(count, seed)[:, :1], 700, 4000)[:, 0] * decay(count, 0.008)


# --- the characters moving (mono) -----------------------------------------------------------------------
def thud(pitch, count, time_constant):
    """A dull knock, with an overtone so small speakers play it too."""
    tone = whistle(np.full(count, pitch)) + 0.5 * whistle(np.full(count, pitch * 2.3))
    return tone * decay(count, time_constant)


def step(surface, seed):
    """A footstep on grass (a soft brush), stone (a tap) or snow (a crunch)."""
    rng = np.random.default_rng(seed)
    count = seconds(0.12)
    if surface == "stone":
        tap = filtered(noise(count, seed)[:, :1], 1500, 5000)[:, 0] * decay(count, 0.006)
        return thud(rng.uniform(260, 340), count, 0.012) * 0.6 + 0.5 * tap
    if surface == "snow":
        grains = np.abs(filtered(noise(count, seed + 1)[:, :1], 30, 200)[:, 0]) ** 2
        return filtered(noise(count, seed)[:, :1], 500, 3000)[:, 0] * grains * fade_in_out(count, 0.01, 0.05)
    brush = filtered(noise(count, seed)[:, :1], 900, 4000)[:, 0] * fade_in_out(count, 0.015, 0.08)
    return brush + 0.3 * thud(rng.uniform(150, 190), count, 0.015)


def stomp(seed):
    """A dragon's heavy foot coming down: a deep thump, and the crunch of the ground under it - the crunch
    is what a laptop's small speakers play, so it carries most of it."""
    rng = np.random.default_rng(seed)
    count = seconds(0.3)
    crunch = filtered(noise(count, seed)[:, :1], 180, 1500, tilt=0.4)[:, 0] * decay(count, 0.035)
    return 0.6 * thud(rng.uniform(70, 90), count, 0.07) + crunch


def wingbeat(seed):
    """A bat's wings: a quick, soft whoosh."""
    count = seconds(0.09)
    swell = np.sin(np.pi * np.linspace(0, 1, count)) ** 2
    return filtered(noise(count, seed)[:, :1], 300, 2000)[:, 0] * swell


CALLS = {"chirps": chirps, "two_notes": two_notes, "trill": trill, "coo": coo, "woodpecker": woodpecker,
         "bee": bee, "drip": drip, "pop": pop}
