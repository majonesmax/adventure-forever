"""The VGA look's band: an early-90s PC sound card's FM chip - two-operator voices for everything, a brassy
lead for the anthem and the fanfare, a reedy one for the march, a bell in the dungeon, plucked chords, a
round bass and quiet drums, played dry, with no room around them (engine/fm.py's voices; engine/band.py
arranges the songs).

Usage: python -m engine.soundcard     -> shots/music/<song>-vga.wav, to listen to
"""

from engine import band as B
from engine import fm as F
from engine.chiptune import Song
from shared.types import Floats, Samples


def fm_brass(pitch: float, length: int) -> Floats:
    tone = F.fm(pitch, length, ratio=1.0, index=3.0, index_decay=0.4)
    return tone * F.env(length, attack=0.03, decay=0.6, sustain=0.6, release=0.05)


def reed(pitch: float, length: int) -> Floats:
    tone = F.fm(pitch, length, ratio=2.0, index=1.6)    # odd harmonics: a clarinet-ish buzz
    return tone * F.env(length, attack=0.02, decay=0.8, sustain=0.7, release=0.05)


def lead(pitch: float, length: int) -> Floats:
    return F.fm(pitch, length, ratio=1.0, index=2.2) * F.env(length, attack=0.01, decay=0.5, sustain=0.65)


def pluck(pitch: float, length: int) -> Floats:
    tone = F.fm(pitch, length, ratio=1.0, index=2.0, index_decay=0.04)
    return tone * F.env(length, decay=0.15, release=0.02)


BAND = B.Band(lead={"anthem": fm_brass, "fanfare": fm_brass, "march": reed, "creep": F.bell, "drive": lead,
                    "default": lead},
              arpeggio=pluck, stab=pluck, pad=lambda pitch, length: F.pad(pitch, length) * 0.15,
              bass=F.bass, drum=F.drum, room=B.dry, mix=(0.30, 0.22, 0.34, 0.22))


def render(song: Song) -> Samples:
    return B.render(song, BAND)


if __name__ == "__main__":
    B.listen(render, "vga")
