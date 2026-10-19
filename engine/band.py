"""A song played by a band - the same song, arranged the same way as engine/chiptune.py arranges it, on
other instruments. Each look but the NES brings its own band (engine/orchestra.py: the SNES's small
orchestra; engine/fm.py: the VGA's PC sound card; engine/toybox.py: paper's toy box), so the music sounds
like the machine on screen, as the pictures do.

A band is its instruments - each instrument(pitch in Hz, length in samples) -> samples - and a room:

    lead      the melody, one per style (a dict: style -> instrument), else lead["default"]
    arpeggio  the quick broken chords (anthem, drive, fanfare) and the slow ones (creep)
    stab      the off-beat chords (march)
    pad       a held chord under everything, or None
    bass      the low notes, in chiptune.py's patterns
    drum      drum(kind, length, rng): k, s, h
    room      room(pcm) -> pcm: the reverb (or none), its tail wrapped round so a loop stays a loop
    mix       how loud the lead, the chords, the bass and the drums are against each other
"""

from typing import Callable, NamedTuple

import numpy as np

from engine.chiptune import RATE, Song, Timing, chord_notes, midi_hz, note_hz, parse_melody
from shared.types import Floats, Instrument, Samples

Drum = Callable[[str, int, np.random.Generator], Floats]   # drum(kind, length, rng) -> the hit
Room = Callable[[Floats], Floats]                           # room(stereo) -> stereo with its reverb


class Band(NamedTuple):
    lead: dict[str, Instrument]   # style -> its melody instrument; "default" for any other style
    arpeggio: Instrument
    stab: Instrument
    pad: Instrument | None
    bass: Instrument
    drum: Drum
    room: Room
    mix: tuple[float, float, float, float]   # lead, chords, bass, drums


LEVEL = 4000             # a song's average loudness: the NES's songs', under the game's sound effects
PEAK = 15000             # ...its loudest moments rounded off towards this
RING = 3.0               # seconds a song may ring on past its end (notes, the room), wrapped or faded


def render(song: Song, band: Band) -> Samples:
    """A song (chiptune.py's notation) -> int16 stereo samples of one pass; a looping song loops cleanly."""
    song = {"drums": "", "style": "march", "loop": True, **song}
    timing = Timing(song)
    chords = song["chords"].split()
    total = len(chords) * timing.bar_n
    length = total + int(RING * RATE)
    lead, chordal, low, drums = (np.zeros(length) for _ in range(4))
    voice = band.lead.get(song["style"], band.lead["default"])
    add_melody(lead, parse_melody(song["melody"]), voice, timing)
    rng = np.random.default_rng(7)
    for bar, symbol in enumerate(chords):
        root, intervals = chord_notes(symbol)
        tones = [root + interval for interval in intervals]
        start = bar * timing.bar_n
        add_chords(chordal, band, song["style"], tones, start, timing)
        add_bass(low, band.bass, song["style"], root, start, timing)
        last_bar_of_fanfare = song["style"] == "fanfare" and bar == len(chords) - 1
        if not last_bar_of_fanfare:
            add_drums(drums, band.drum, song["drums"], start, timing, rng)
    return mix_down((lead, chordal, low, drums), band, total, song["loop"])


def play(track: Floats, start: int, instrument: Instrument, pitch: float, length: int) -> None:
    """Add a note to a track, cut off at the track's end."""
    length = min(length, len(track) - start)
    if length > 0:
        track[start:start + length] += instrument(pitch, length)


def add_melody(lead: Floats, tokens: list[str], voice: Instrument, timing: Timing) -> None:
    """Eighth-note tokens: "-" holds the note before it, "." rests."""
    index = 0
    while index < len(tokens):
        after = index + 1
        while after < len(tokens) and tokens[after] == "-":
            after += 1
        if tokens[index] not in ("-", "."):
            start = timing.at(2 * index)
            play(lead, start, voice, note_hz(tokens[index]), timing.at(2 * after) - start)
        index = after


def add_chords(chordal: Floats, band: Band, style: str, tones: list[int], bar_start: int,
               timing: Timing) -> None:
    """The chords, by style: a quick arpeggio, off-beat stabs, or a slow broken chord; and the pad."""
    if style in ("anthem", "drive", "fanfare"):
        sequence = tones + [tones[0] + 12, tones[1] + 12]
        for sixteenth in range(16):
            midi = sequence[sixteenth % len(sequence)] + 12
            play(chordal, bar_start + timing.at(sixteenth), band.arpeggio, midi_hz(midi), timing.at(3))
    elif style == "march":
        for sixteenth in (2, 6, 10, 14):
            for midi in tones:
                play(chordal, bar_start + timing.at(sixteenth), band.stab, midi_hz(midi + 12), timing.at(2))
    else:   # creep, and any other: a slow broken chord in eighths
        for sixteenth in range(0, 16, 2):
            midi = tones[(sixteenth // 2) % len(tones)] + 12
            play(chordal, bar_start + timing.at(sixteenth), band.arpeggio, midi_hz(midi), timing.at(6))
    if band.pad is not None:
        for midi in tones:
            play(chordal, bar_start, band.pad, midi_hz(midi + 12), timing.bar_n + timing.at(2))


def add_bass(low: Floats, bass: Instrument, style: str, root: int, bar_start: int, timing: Timing) -> None:
    """The chord's root an octave down, in the same patterns as the NES's triangle."""
    if style in ("march", "anthem", "fanfare"):
        pattern = [(0, root - 12), (4, root - 5), (8, root - 12), (12, root - 5)]
    elif style == "drive":
        pattern = [(sixteenth, root - 12 if sixteenth % 4 == 0 else root) for sixteenth in range(0, 16, 2)]
    else:
        pattern = [(0, root - 12), (12, root - 10)]
    for index, (sixteenth, midi) in enumerate(pattern):
        until = pattern[index + 1][0] if index + 1 < len(pattern) else 16
        start = bar_start + timing.at(sixteenth)
        play(low, start, bass, midi_hz(midi), bar_start + timing.at(until) - start)


def add_drums(drums: Floats, drum: Drum, pattern: str, bar_start: int, timing: Timing,
              rng: np.random.Generator) -> None:
    """One bar of the drum pattern (16 steps: k kick, s snare, h hi-hat, . nothing)."""
    for sixteenth, kind in enumerate(pattern):
        if kind == ".":
            continue
        start = bar_start + timing.at(sixteenth)
        length = min(int(0.4 * RATE), len(drums) - start)
        drums[start:start + length] += drum(kind, length, rng)


def mix_down(tracks: tuple[Floats, Floats, Floats, Floats], band: Band, total: int, loop: bool) -> Samples:
    """The four tracks -> stereo in the band's room: a loop's tail wraps onto its start, a jingle fades
    out. As loud on average as the NES's songs, its peaks rounded off below PEAK."""
    lead, chordal, low, drums = (track * share for track, share in zip(tracks, band.mix))
    left = lead + 0.9 * chordal + low + drums
    right = 0.95 * lead + 1.1 * chordal + low + drums
    pcm = band.room(np.stack([left, right], axis=1))
    if loop:
        body = pcm[:total].copy()
        tail = pcm[total:]
        body[:len(tail)] += tail[:total]
        pcm = body
        fade_out, fade_in = int(0.008 * RATE), int(0.002 * RATE)    # no click where it wraps
        pcm[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
        pcm[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    else:
        pcm[-int(0.6 * RATE):] *= np.linspace(1, 0, int(0.6 * RATE))[:, None]
    pcm *= LEVEL / max(1e-9, np.sqrt((pcm ** 2).mean()))
    return (PEAK * np.tanh(pcm / PEAK)).astype(np.int16)


def dry(pcm: Floats) -> Floats:
    """No room at all (a PC's sound card)."""
    return pcm


def reverb(delays: tuple[float, ...], feedback: float, wet: float) -> Room:
    """A room: echoes at uneven `delays` (seconds), each fed back a few times, mixed in at `wet`."""
    def room(pcm: Floats) -> Floats:
        out = pcm.copy()
        for delay_seconds in delays:
            delay = int(delay_seconds * RATE)
            for repeat in range(1, 5):
                shift = delay * repeat
                if shift >= len(pcm):
                    break
                out[shift:] += pcm[:-shift] * wet * feedback ** repeat
        return out
    return room


def listen(render_song: Callable[[Song], Samples], label: str) -> None:
    """Every built-in song through a band, as WAVs in shots/music/<song>-<label>.wav (looping songs twice)."""
    import os
    import wave
    from engine import paths
    from engine.chiptune import SONGS
    folder = os.path.join(paths.SHOTS, "music")
    os.makedirs(folder, exist_ok=True)
    for name, song in SONGS.items():
        pcm = render_song(song)
        if song["loop"]:
            pcm = np.concatenate([pcm, pcm])
        path = os.path.join(folder, f"{name}-{label}.wav")
        with wave.open(path, "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(pcm.tobytes())
        print(f"{path}  {len(pcm) / RATE:.1f} s")
