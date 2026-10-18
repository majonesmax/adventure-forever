"""Original chiptune music for Adventure (no outside music): an NES-style synth and five songs.

Voices, like the NES sound chip: pulse 1 (melody, 25% duty, gentle vibrato), pulse 2 (arpeggios / stabs,
12.5% duty), a 4-bit stepped triangle (bass, and the kick drum as a fast pitch drop), noise (snare, hi-hat).
A song is a tempo, one chord per bar, a melody in eighth notes and a drum pattern in sixteenths; the bass line
and the arpeggios are derived from the chords.

Melody tokens (one per eighth note): a note like E5 / F#4 / Bb5, "-" holds the previous note, "." rests.
Drums (16 per bar): k kick, s snare, h hi-hat, . nothing.

Usage: python chiptune.py              -> shots/music/<song>.wav (two loops each) to listen to
       python chiptune.py --play title
"""

import os
import sys

import numpy as np

RATE = 31440
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
CHORDS = {"": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "dim": (0, 3, 6)}

SONGS = {
    "title": dict(bpm=112, style="anthem", loop=True, drums="k.h.s.h.k.k.s.h.",
                  chords="C G Am F C G F G",
                  melody="""E5 - G5 - C6 - B5 A5 | G5 - - D5 G5 - F5 E5 | E5 - A5 - C6 - B5 A5 |
                            A5 - G5 F5 E5 - D5 - | E5 - G5 - C6 - D6 E6 | D6 - B5 - G5 - A5 B5 |
                            C6 - A5 - F5 - G5 A5 | G5 - - - B4 C5 D5 -"""),
    "overworld": dict(bpm=138, style="march", loop=True, drums="k.h.s.h.k.h.s.hh",
                      chords="G G C G G D Em D C G C D G D G G",
                      melody="""D5 - G5 - G5 A5 B5 G5 | D6 - - B5 G5 - D5 - | E5 - G5 - C6 - B5 A5 |
                                B5 - - - G5 - - - | D5 - G5 - G5 A5 B5 C6 | D6 - - C6 B5 - A5 - |
                                G5 - E5 - B5 - G5 - | A5 - - - F#5 - - - | G5 - E5 - C6 - E6 - |
                                D6 - B5 - G5 - B5 - | C6 - E6 - G6 - E6 C6 | D6 - - - A5 - F#5 - |
                                G5 - B5 - D6 - B5 G5 | A5 - F#5 - D5 - F#5 A5 | G5 - D5 - B4 - D5 - |
                                G5 - - - . . . ."""),
    "dungeon": dict(bpm=96, style="creep", loop=True, drums="k.......k...h...",
                    chords="Am Am F E Am Am Dm E",
                    melody=""". . E5 - - - C5 - | B4 - - - A4 - . . | . . F5 - - - E5 - |
                              D5 - - - G#4 - . . | . . A5 - - - G5 - | E5 - - - C5 - . . |
                              D5 - F5 - A5 - G5 F5 | E5 - - - G#4 - B4 -"""),
    "final": dict(bpm=150, style="drive", loop=True, drums="k.hks.hhk.hks.hk",
                  chords="Dm Bb Gm A Dm Bb Gm A",
                  melody="""D5 - F5 - A5 - D6 - | C6 - Bb5 - A5 - F5 - | G5 - Bb5 - D6 - C6 Bb5 |
                            A5 - - - C#6 - E6 - | F6 - E6 D6 C6 - A5 - | Bb5 - A5 G5 F5 - D5 - |
                            G5 - A5 - Bb5 - C6 D6 | C#6 - - - A5 - - -"""),
    "win": dict(bpm=150, style="fanfare", loop=False, drums="k...s...k.s.k...",
                chords="C C C", melody="G5 C6 E6 G6 - - E6 G6 | C7 - - - - - - - | - - - - . . . ."),
}


def note_hz(name):
    """'F#4' / 'Bb5' / 'C6' -> Hz (A4 = 440)."""
    letter, rest = name[0], name[1:]
    semi = NOTE[letter]
    while rest and rest[0] in "#b":
        semi += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    midi = 12 * (int(rest) + 1) + semi
    return 440.0 * 2 ** ((midi - 69) / 12)


def chord_notes(sym):
    """'Am' -> (root midi in octave 3, intervals); 'Bb' / 'F#m' work too."""
    root = sym[0]
    accidental = sym[1] if len(sym) > 1 and sym[1] in "#b" else ""
    quality = sym[1 + len(accidental):]
    semitone = NOTE[root] + {"#": 1, "b": -1, "": 0}[accidental]
    return 48 + semitone, CHORDS[quality]


def midi_hz(midi):
    """A MIDI note number (69 = A4) -> Hz."""
    return 440.0 * 2 ** ((midi - 69) / 12)


def pulse(freq, length, duty, start_phase=0.0, vibrato=0.0):
    """A square-ish wave, high for `duty` of each cycle; vibrato fades in after 0.15 s."""
    seconds = np.arange(length) / RATE
    wobble = vibrato * np.sin(2 * np.pi * 5.5 * seconds) * np.clip((seconds - 0.15) / 0.2, 0, 1)
    freqs = freq * (1 + wobble)
    phase = (np.cumsum(freqs) / RATE + start_phase) % 1.0
    return np.where(phase < duty, 1.0, -1.0)


def triangle(freq, length):
    if np.ndim(freq) == 0:
        freq = np.full(length, freq)
    phase = (np.cumsum(freq) / RATE) % 1.0
    tri = 1 - 4 * np.abs(phase - 0.5)                   # -1..1
    return np.round((tri + 1) * 7.5) / 7.5 - 1           # 16 steps, like the NES triangle


def envelope(length, attack=0.004, decay=0.18, sustain=0.55, release=0.03):
    """A note's loudness over time: a quick rise, a fall to `sustain`, a short fade at the end."""
    seconds = np.arange(length) / RATE
    after_attack = sustain + (1 - sustain) * np.exp(-(seconds - attack) / decay)
    env = np.where(seconds < attack, seconds / attack, after_attack)
    release_n = int(release * RATE)
    if length > release_n:
        env[-release_n:] *= np.linspace(1, 0, release_n)
    return env


def drum(kind, length, rng):
    seconds = np.arange(length) / RATE
    if kind == "k":  # triangle pitch drop
        freqs = 55 + 120 * np.exp(-seconds / 0.03)
        return triangle(freqs, length) * np.exp(-seconds / 0.09) * 1.1
    noise = rng.choice([-1.0, 1.0], length)
    if kind == "s":
        return noise * np.exp(-seconds / 0.07) * 0.7
    if kind == "h":
        return noise * np.exp(-seconds / 0.018) * 0.35
    return np.zeros(length)


def parse_melody(text):
    return [tok for bar in text.split("|") for tok in bar.split()]


def render(name):
    """-> int16 stereo PCM of one pass of the song (loops cleanly when played back to back). name: one of
    SONGS, or a song dict in the same form (a world's own, from its music.json)."""
    song = SONGS[name] if isinstance(name, str) else name
    song = {"drums": "", "style": "march", "loop": True, **song}  # what a world's song may leave out
    timing = Timing(song)
    chords = song["chords"].split()
    total = len(chords) * timing.bar_n
    tail = int(1.5 * RATE) if not song["loop"] else 0  # a jingle rings on after its last bar
    lead, harmony, bass, drums = (np.zeros(total + tail) for _ in range(4))
    rng = np.random.default_rng(7)
    add_melody(lead, parse_melody(song["melody"]), timing, total + tail)
    for bar, symbol in enumerate(chords):
        root, intervals = chord_notes(symbol)
        start = bar * timing.bar_n
        tones = [root + interval for interval in intervals]
        add_bass(bass, song["style"], root, start, timing)
        add_harmony(harmony, song["style"], tones, start, timing)
        last_bar_of_fanfare = song["style"] == "fanfare" and bar == len(chords) - 1
        if not last_bar_of_fanfare:
            add_drums(drums, song["drums"], start, timing, rng)
    return mix_down(lead, harmony, bass, drums, song["loop"])


class Timing:
    """A song's tempo in samples: a sixteenth note, a bar."""

    def __init__(self, song):
        self.step = 60.0 / song["bpm"] / 4  # a sixteenth note, in seconds
        self.bar_n = int(round(16 * self.step * RATE))

    def at(self, sixteenth):
        """A sixteenth-note index -> the sample it starts on."""
        return int(round(sixteenth * self.step * RATE))


def add_melody(lead, tokens, timing, length):
    """Pulse 1: eighth-note tokens; "-" holds the note before it, "." rests."""
    i = 0
    while i < len(tokens):
        token = tokens[i]
        j = i + 1
        while j < len(tokens) and tokens[j] == "-":
            j += 1
        if token not in ("-", "."):
            start, end = timing.at(2 * i), min(timing.at(2 * j), length)
            note = pulse(note_hz(token), end - start, 0.25, vibrato=0.004)
            lead[start:end] += note * envelope(end - start, sustain=0.6)
        i = j


def add_bass(bass, style, root, bar_start, timing):
    """The triangle: the chord's root an octave down, in the style's pattern."""
    if style in ("march", "anthem", "fanfare"):
        pattern = [(0, root - 12), (4, root - 5), (8, root - 12), (12, root - 5)]
    elif style == "drive":
        pattern = [(k, root - 12 if k % 4 == 0 else root) for k in range(0, 16, 2)]
    else:  # creep: long low root, a step up near the end
        pattern = [(0, root - 12), (12, root - 10)]
    for index, (sixteenth, midi) in enumerate(pattern):
        until = pattern[index + 1][0] if index + 1 < len(pattern) else 16
        start = bar_start + timing.at(sixteenth)
        end = bar_start + timing.at(until) - int(0.01 * RATE)  # a tiny gap between notes
        note = triangle(midi_hz(midi), end - start)
        bass[start:end] += note * envelope(end - start, decay=0.5, sustain=0.85, release=0.01)


def add_harmony(harmony, style, tones, bar_start, timing):
    """Pulse 2: an arpeggio, chord stabs or a broken chord, by style."""
    if style in ("anthem", "drive", "fanfare"):  # sixteenth-note arpeggio, up an octave
        sequence = (tones + [tones[0] + 12, tones[1] + 12])
        for sixteenth in range(16):
            midi = sequence[sixteenth % len(sequence)] + 12
            start, end = bar_start + timing.at(sixteenth), bar_start + timing.at(sixteenth + 1)
            note = pulse(midi_hz(midi), end - start, 0.125)
            harmony[start:end] += note * envelope(end - start, decay=0.05, sustain=0.3, release=0.005)
    elif style == "march":  # off-beat chord stabs
        for sixteenth in (2, 6, 10, 14):
            start, end = bar_start + timing.at(sixteenth), bar_start + timing.at(sixteenth + 1)
            for midi in tones:
                note = pulse(midi_hz(midi + 12), end - start, 0.125)
                stab = envelope(end - start, decay=0.04, sustain=0.2, release=0.005)
                harmony[start:end] += note * stab * 0.5
    else:  # creep: slow broken chord in eighths
        for sixteenth in range(0, 16, 2):
            midi = tones[(sixteenth // 2) % len(tones)] + 12
            start, end = bar_start + timing.at(sixteenth), bar_start + timing.at(sixteenth + 2)
            note = pulse(midi_hz(midi), end - start, 0.125)
            harmony[start:end] += note * envelope(end - start, decay=0.12, sustain=0.25)


def add_drums(drums, pattern, bar_start, timing, rng):
    """One bar of the drum pattern (16 steps: k kick, s snare, h hi-hat, . nothing)."""
    for sixteenth, kind in enumerate(pattern):
        if kind == ".":
            continue
        start = bar_start + timing.at(sixteenth)
        length = min(int(0.2 * RATE), len(drums) - start)
        drums[start:start + length] += drum(kind, length, rng)


def mix_down(lead, harmony, bass, drums, loop):
    """The four voices -> int16 stereo, pulse 2 a touch to the right; faded so it loops (or ends) cleanly."""
    left = 0.24 * lead + 0.10 * harmony * 0.9 + 0.30 * bass + 0.16 * drums
    right = 0.24 * lead + 0.10 * harmony * 1.1 + 0.30 * bass + 0.16 * drums
    pcm = np.stack([left, right], axis=1)
    pcm *= 12000 / max(1e-9, np.abs(pcm).max())  # a typical NES-music level under the 2600 SFX
    if loop:  # no click where the loop wraps: 8 ms out at the end, 2 ms in at the start
        pcm[-int(0.008 * RATE):] *= np.linspace(1, 0, int(0.008 * RATE))[:, None]
        pcm[:int(0.002 * RATE)] *= np.linspace(0, 1, int(0.002 * RATE))[:, None]
    else:  # the jingle rings out, then fades to silence instead of stopping dead
        pcm[-int(0.3 * RATE):] *= np.linspace(1, 0, int(0.3 * RATE))[:, None]
    return pcm.astype(np.int16)


def render_all():
    return {name: render(name) for name in SONGS}


def main():
    import wave
    from engine import paths
    out = os.path.join(paths.SHOTS, "music")
    os.makedirs(out, exist_ok=True)
    if sys.argv[1:2] == ["--play"]:
        import sounddevice as sd
        pcm = render(sys.argv[2])
        sd.play(np.concatenate([pcm, pcm]) if SONGS[sys.argv[2]]["loop"] else pcm, RATE, blocking=True)
        return
    for name in SONGS:
        pcm = render(name)
        if SONGS[name]["loop"]:
            pcm = np.concatenate([pcm, pcm])
        path = os.path.join(out, f"{name}.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm.tobytes())
        print(f"{path}  {len(pcm) / RATE:.1f} s")


if __name__ == "__main__":
    main()
