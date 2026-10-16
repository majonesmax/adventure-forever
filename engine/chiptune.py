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
                  melody="""E5 - G5 - C6 - B5 A5 | G5 - - D5 G5 - F5 E5 | E5 - A5 - C6 - B5 A5 | A5 - G5 F5 E5 - D5 - |
                            E5 - G5 - C6 - D6 E6 | D6 - B5 - G5 - A5 B5 | C6 - A5 - F5 - G5 A5 | G5 - - - B4 C5 D5 -"""),
    "overworld": dict(bpm=138, style="march", loop=True, drums="k.h.s.h.k.h.s.hh",
                      chords="G G C G G D Em D C G C D G D G G",
                      melody="""D5 - G5 - G5 A5 B5 G5 | D6 - - B5 G5 - D5 - | E5 - G5 - C6 - B5 A5 | B5 - - - G5 - - - |
                                D5 - G5 - G5 A5 B5 C6 | D6 - - C6 B5 - A5 - | G5 - E5 - B5 - G5 - | A5 - - - F#5 - - - |
                                G5 - E5 - C6 - E6 - | D6 - B5 - G5 - B5 - | C6 - E6 - G6 - E6 C6 | D6 - - - A5 - F#5 - |
                                G5 - B5 - D6 - B5 G5 | A5 - F#5 - D5 - F#5 A5 | G5 - D5 - B4 - D5 - | G5 - - - . . . ."""),
    "dungeon": dict(bpm=96, style="creep", loop=True, drums="k.......k...h...",
                    chords="Am Am F E Am Am Dm E",
                    melody=""". . E5 - - - C5 - | B4 - - - A4 - . . | . . F5 - - - E5 - | D5 - - - G#4 - . . |
                              . . A5 - - - G5 - | E5 - - - C5 - . . | D5 - F5 - A5 - G5 F5 | E5 - - - G#4 - B4 -"""),
    "final": dict(bpm=150, style="drive", loop=True, drums="k.hks.hhk.hks.hk",
                  chords="Dm Bb Gm A Dm Bb Gm A",
                  melody="""D5 - F5 - A5 - D6 - | C6 - Bb5 - A5 - F5 - | G5 - Bb5 - D6 - C6 Bb5 | A5 - - - C#6 - E6 - |
                            F6 - E6 D6 C6 - A5 - | Bb5 - A5 G5 F5 - D5 - | G5 - A5 - Bb5 - C6 D6 | C#6 - - - A5 - - -"""),
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
    acc = sym[1] if len(sym) > 1 and sym[1] in "#b" else ""
    quality = sym[1 + len(acc):]
    semi = NOTE[root] + (1 if acc == "#" else -1 if acc == "b" else 0)
    return 48 + semi, CHORDS[quality]


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def pulse(freq, n, duty, t0=0.0, vibrato=0.0):
    t = np.arange(n) / RATE
    f = freq * (1 + vibrato * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - 0.15) / 0.2, 0, 1))
    phase = (np.cumsum(f) / RATE + t0) % 1.0
    return np.where(phase < duty, 1.0, -1.0)


def triangle(freq, n):
    if np.ndim(freq) == 0:
        freq = np.full(n, freq)
    phase = (np.cumsum(freq) / RATE) % 1.0
    tri = 1 - 4 * np.abs(phase - 0.5)                   # -1..1
    return np.round((tri + 1) * 7.5) / 7.5 - 1           # 16 steps, like the NES triangle


def envelope(n, attack=0.004, decay=0.18, sustain=0.55, release=0.03):
    t = np.arange(n) / RATE
    env = np.where(t < attack, t / attack, sustain + (1 - sustain) * np.exp(-(t - attack) / decay))
    rel = int(release * RATE)
    if n > rel:
        env[-rel:] *= np.linspace(1, 0, rel)
    return env


def drum(kind, n, rng):
    t = np.arange(n) / RATE
    if kind == "k":  # triangle pitch drop
        f = 55 + 120 * np.exp(-t / 0.03)
        return triangle(f, n) * np.exp(-t / 0.09) * 1.1
    noise = rng.choice([-1.0, 1.0], n)
    if kind == "s":
        return noise * np.exp(-t / 0.07) * 0.7
    if kind == "h":
        return noise * np.exp(-t / 0.018) * 0.35
    return np.zeros(n)


def parse_melody(text):
    return [tok for bar in text.split("|") for tok in bar.split()]


def render(name):
    """-> int16 stereo PCM of one pass of the song (loops cleanly when played back to back)."""
    s = SONGS[name]
    step = 60.0 / s["bpm"] / 4                        # a sixteenth note, in seconds
    chords = s["chords"].split()
    bars = len(chords)
    bar_n = int(round(16 * step * RATE))
    total = bars * bar_n
    tail = int(1.5 * RATE) if not s["loop"] else 0
    lead, harm, bass, drums = (np.zeros(total + tail) for _ in range(4))
    rng = np.random.default_rng(7)
    sx = lambda k: int(round(k * step * RATE))       # sixteenth index -> sample

    # melody: eighth-note tokens, "-" extends the note
    toks = parse_melody(s["melody"])
    i = 0
    while i < len(toks):
        tok = toks[i]
        j = i + 1
        while j < len(toks) and toks[j] == "-":
            j += 1
        if tok not in ("-", "."):
            a, b = sx(2 * i), min(sx(2 * j), total + tail)
            lead[a:b] += pulse(note_hz(tok), b - a, 0.25, vibrato=0.004) * envelope(b - a, sustain=0.6)
        i = j

    for bar, sym in enumerate(chords):
        root, ivs = chord_notes(sym)
        base = bar * bar_n
        tones = [root + iv for iv in ivs]
        # bass (triangle)
        if s["style"] in ("march", "anthem", "fanfare"):
            pattern = [(0, root - 12), (4, root - 5), (8, root - 12), (12, root - 5)]
        elif s["style"] == "drive":
            pattern = [(k, root - 12 if k % 4 == 0 else root) for k in range(0, 16, 2)]
        else:  # creep: long low root, a step up near the end
            pattern = [(0, root - 12), (12, root - 10)]
        for idx, (k, m) in enumerate(pattern):
            end = pattern[idx + 1][0] if idx + 1 < len(pattern) else 16
            a, b = base + sx(k), base + sx(end) - int(0.01 * RATE)
            bass[a:b] += triangle(midi_hz(m), b - a) * envelope(b - a, decay=0.5, sustain=0.85, release=0.01)
        # harmony (pulse 2)
        if s["style"] in ("anthem", "drive", "fanfare"):   # sixteenth-note arpeggio, up an octave
            seq = (tones + [tones[0] + 12, tones[1] + 12])
            for k in range(16):
                m = seq[k % len(seq)] + 12
                a, b = base + sx(k), base + sx(k + 1)
                harm[a:b] += pulse(midi_hz(m), b - a, 0.125) * envelope(b - a, decay=0.05, sustain=0.3, release=0.005)
        elif s["style"] == "march":                        # off-beat chord stabs
            for k in (2, 6, 10, 14):
                a, b = base + sx(k), base + sx(k + 1)
                for m in tones:
                    harm[a:b] += pulse(midi_hz(m + 12), b - a, 0.125) * envelope(b - a, decay=0.04, sustain=0.2,
                                                                               release=0.005) * 0.5
        else:                                              # creep: slow broken chord in eighths
            for k in range(0, 16, 2):
                m = tones[(k // 2) % len(tones)] + 12
                a, b = base + sx(k), base + sx(k + 2)
                harm[a:b] += pulse(midi_hz(m), b - a, 0.125) * envelope(b - a, decay=0.12, sustain=0.25)
        # drums
        if not (s["style"] == "fanfare" and bar == bars - 1):
            for k, ch in enumerate(s["drums"]):
                if ch != ".":
                    a = base + sx(k)
                    n = min(int(0.2 * RATE), len(drums) - a)
                    drums[a:a + n] += drum(ch, n, rng)

    mixl = 0.24 * lead + 0.10 * harm * 0.9 + 0.30 * bass + 0.16 * drums
    mixr = 0.24 * lead + 0.10 * harm * 1.1 + 0.30 * bass + 0.16 * drums  # pulse 2 a touch to the right
    pcm = np.stack([mixl, mixr], axis=1)
    pcm *= 12000 / max(1e-9, np.abs(pcm).max())          # a typical NES-music level under the 2600 SFX
    if s["loop"]:  # no click where the loop wraps: 8 ms out at the end, 2 ms in at the start
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
