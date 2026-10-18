"""The SNES look's band: a small orchestra, in the spirit of the sampled instruments 16-bit adventures had -
brass for the anthem and the fanfare, a flute for the march, strings, a harp, a celesta in the dungeon,
pizzicato and a contrabass, timpani - in a hall (engine/band.py arranges the songs).

Usage: python -m engine.orchestra     -> shots/music/<song>-snes.wav, to listen to
"""

import numpy as np

from engine import band as B
from engine.chiptune import RATE
from engine.fm import env, fm

STRING_HARMONICS = 8


def harmonics(pitch, length, stops, vibrato=0.0, detune=0.0):
    """A tone made by adding up harmonics, (number, loudness) - a string's overtones, a flute's few."""
    time = np.arange(length) / RATE
    wobble = 1 + vibrato * np.sin(2 * np.pi * 5.2 * time) * np.clip((time - 0.2) / 0.3, 0, 1)
    phase = 2 * np.pi * np.cumsum(pitch * (1 + detune) * wobble) / RATE
    tone = sum(loudness * np.sin(phase * number) for number, loudness in stops)
    return tone / sum(loudness for _number, loudness in stops)


def strings(pitch, length, attack=0.12):
    stops = [(number, 1 / number) for number in range(1, STRING_HARMONICS + 1)]   # a softened sawtooth
    flat = harmonics(pitch, length, stops, vibrato=0.006, detune=-0.002)   # two players a hair apart
    sharp = harmonics(pitch, length, stops, vibrato=0.006, detune=0.002)
    tone = 0.5 * (flat + sharp)
    return tone * env(length, attack=attack, decay=1.5, sustain=0.8, release=0.15)


def violin(pitch, length):
    return strings(pitch, length, attack=0.04)


def flute(pitch, length):
    breath = np.random.default_rng(int(pitch)).normal(size=length) * 0.03
    tone = harmonics(pitch, length, [(1, 1.0), (2, 0.25), (3, 0.08)], vibrato=0.008)
    return (tone + breath) * env(length, attack=0.05, decay=1.0, sustain=0.85, release=0.08)


def brass(pitch, length):
    tone = fm(pitch, length, ratio=1.0, index=2.4) * 0.7 + fm(pitch, length, ratio=2.0, index=0.8) * 0.3
    return tone * env(length, attack=0.04, decay=0.8, sustain=0.75, release=0.08)


def harp(pitch, length):
    return fm(pitch, length, ratio=1.0, index=0.8, index_decay=0.3) * env(length, decay=0.9, release=0.05)


def celesta(pitch, length):
    return fm(pitch * 2, length, ratio=3.5, index=1.4, index_decay=0.5) * env(length, decay=1.2, release=0.1)


def pizzicato(pitch, length):
    return fm(pitch, length, ratio=1.0, index=1.2, index_decay=0.05) * env(length, decay=0.12, release=0.02)


def contrabass(pitch, length):
    tone = fm(pitch, length, ratio=1.0, index=1.0, index_decay=0.2)
    return tone * env(length, attack=0.01, decay=0.6, sustain=0.5, release=0.05)


def drum(kind, length, rng):
    time = np.arange(length) / RATE
    if kind == "k":   # timpani
        pitch = 62 + 30 * np.exp(-time / 0.05)
        return np.sin(2 * np.pi * np.cumsum(pitch) / RATE) * np.exp(-time / 0.3)
    if kind == "s":   # a soft orchestral snare
        rattle = np.convolve(rng.uniform(-1, 1, length), np.ones(4) / 4, "same")
        return rattle * np.exp(-time / 0.08) * 0.45
    if kind == "h":   # a shaker
        return np.diff(rng.uniform(-1, 1, length), prepend=0) * np.exp(-time / 0.025) * 0.12
    return np.zeros(length)


BAND = B.Band(lead={"anthem": brass, "fanfare": brass, "march": flute, "creep": celesta, "drive": violin,
                    "default": flute},
              arpeggio=harp, stab=pizzicato, pad=lambda pitch, length: strings(pitch, length) * 0.25,
              bass=contrabass, drum=drum,
              room=B.reverb((0.031, 0.047, 0.071, 0.113, 0.173), feedback=0.45, wet=0.3),
              mix=(0.30, 0.22, 0.34, 0.24))


def render(song):
    return B.render(song, BAND)


if __name__ == "__main__":
    B.listen(render, "snes")
