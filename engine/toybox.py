"""The paper look's band: a child's toy box - a music box plays the tune, a glockenspiel the chords, a
little marimba the bass, and a woodblock, a shaker and a toy drum keep time, in a small bedroom
(engine/band.py arranges the songs).

Usage: python -m engine.toybox     -> shots/music/<song>-paper.wav, to listen to
"""

import numpy as np

from engine import band as B
from engine.chiptune import RATE
from engine.fm import env, fm


def music_box(pitch, length):
    """A comb's tooth plucked: bright, bell-like, ringing on whatever the note's length."""
    tine = fm(pitch * 2, length, ratio=4.0, index=1.0, index_decay=0.08)
    body = fm(pitch * 2, length, ratio=1.0, index=0.3, index_decay=0.4)
    return (0.4 * tine + body) * env(length, attack=0.002, decay=0.6, release=0.05)


def glockenspiel(pitch, length):
    bar = fm(pitch * 2, length, ratio=2.76, index=0.8, index_decay=0.2)   # a metal bar's uneven overtone
    return bar * env(length, decay=0.35, release=0.03)


def marimba(pitch, length):
    """A wooden bar: the note and its fourth harmonic, which dies first."""
    time = np.arange(length) / RATE
    overtone = 0.3 * np.sin(2 * np.pi * pitch * 4 * time) * np.exp(-time / 0.03)
    tone = np.sin(2 * np.pi * pitch * time) + overtone
    return tone * env(length, attack=0.003, decay=0.35, release=0.03)


def drum(kind, length, rng):
    time = np.arange(length) / RATE
    if kind == "k":   # a toy drum
        pitch = 130 + 60 * np.exp(-time / 0.02)
        return np.sin(2 * np.pi * np.cumsum(pitch) / RATE) * np.exp(-time / 0.08) * 0.8
    if kind == "s":   # a woodblock
        return np.sin(2 * np.pi * 900 * time) * np.exp(-time / 0.02) * 0.5
    if kind == "h":   # a shaker
        return np.diff(rng.uniform(-1, 1, length), prepend=0) * np.exp(-time / 0.02) * 0.1
    return np.zeros(length)


BAND = B.Band(lead={"default": music_box}, arpeggio=glockenspiel, stab=glockenspiel, pad=None,
              bass=marimba, drum=drum, room=B.reverb((0.013, 0.021, 0.034), feedback=0.3, wet=0.25),
              mix=(0.36, 0.20, 0.30, 0.22))


def render(song):
    return B.render(song, BAND)


if __name__ == "__main__":
    B.listen(render, "paper")
