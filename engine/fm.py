"""An FM synth for songs in the early-90s PC sound (an AdLib card's two-operator FM): soft electric piano,
glassy bells, warm pads, round bass, quiet drums - and an echo, for empty rooms.

Songs use chiptune.py's notation - a tempo, one chord per bar, a melody in eighth notes ("-" holds, "." rests),
16 drum steps per bar (k kick, s snare, h hi-hat, . nothing) - with these arrangement styles:
    ambient    a pad holds each bar's chord, the melody on a bell, a soft bass under it
    ostinato   an electric piano repeats the chord in eighths; bass on the beats; the melody on top
    drone      a low pad drone on each chord's root and fifth, the melody on a distant bell
    chime      bells arpeggiate the chords over a pad - for a jingle (loop: false)
A world brings its songs in world/music.json (content/world.py); engine/music.py plays them.

Usage: python engine/fm.py path/to/music.json [song]   -> shots/music/<song>.wav to listen to
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, as a script
from engine.chiptune import RATE, chord_notes, midi_hz, note_hz, parse_melody  # noqa: E402


def env(n, attack=0.005, decay=0.6, sustain=0.0, release=0.05):
    t = np.arange(n) / RATE
    e = np.where(t < attack, t / max(attack, 1e-6), sustain + (1 - sustain) * np.exp(-(t - attack) / decay))
    rel = min(n, int(release * RATE))
    if rel:
        e[-rel:] *= np.linspace(1, 0, rel)
    return e


def fm(freq, n, ratio=1.0, index=1.0, index_decay=None, detune=0.0):
    """Two-operator FM: a sine carrier, phase-modulated by a sine at freq * ratio, the modulation `index`
    fading over index_decay seconds (None: steady) - bright at the attack, mellow as it rings."""
    t = np.arange(n) / RATE
    f = freq * (1 + detune)
    depth = index * (np.exp(-t / index_decay) if index_decay else 1.0)
    return np.sin(2 * np.pi * f * t + depth * np.sin(2 * np.pi * f * ratio * t))


def epiano(freq, n):
    tine = 0.15 * fm(freq, n, ratio=14.0, index=1.2, index_decay=0.02)
    return (fm(freq, n, ratio=1.0, index=1.8, index_decay=0.35) + tine) * env(n, decay=1.1, sustain=0.15)


def bell(freq, n):
    return fm(freq, n, ratio=3.5, index=2.2, index_decay=0.9) * env(n, decay=2.4, release=0.2)


def pad(freq, n):
    a = fm(freq, n, ratio=1.0, index=0.7, detune=-0.003)
    b = fm(freq, n, ratio=2.0, index=0.4, detune=0.003)
    return 0.5 * (a + b) * env(n, attack=0.7, decay=3.0, sustain=0.8, release=0.5)


def bass(freq, n):
    return fm(freq, n, ratio=1.0, index=1.4, index_decay=0.18) * env(n, decay=0.9, sustain=0.45, release=0.04)


def drum(kind, n, rng):
    t = np.arange(n) / RATE
    if kind == "k":  # a soft, low thump
        f = 46 + 70 * np.exp(-t / 0.04)
        return np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t / 0.16)
    noise = rng.uniform(-1, 1, n)
    if kind == "s":
        return np.convolve(noise, np.ones(3) / 3, "same") * np.exp(-t / 0.09) * 0.35
    if kind == "h":
        return np.diff(noise, prepend=0) * np.exp(-t / 0.02) * 0.12
    return np.zeros(n)


def echo(x, seconds=0.33, feedback=0.38, mix=0.32):
    """A feedback delay, for the empty-office reverb (x: (n, 2), in place)."""
    d = int(seconds * RATE)
    out = x.copy()
    for k in range(1, 6):
        if d * k >= len(x):
            break
        out[d * k:] += x[:-d * k] * (feedback ** k) * mix
    return out


def render(song):
    """A song dict -> int16 stereo PCM of one pass (loops cleanly: the echo's tail wraps round to the start)."""
    s = song
    step = 60.0 / s["bpm"] / 4
    chords = s["chords"].split()
    bar_n = int(round(16 * step * RATE))
    total = len(chords) * bar_n
    tail = int(3.0 * RATE)
    mel, chordal, low, drums = (np.zeros(total + tail) for _ in range(4))
    rng = np.random.default_rng(11)
    sx = lambda k: int(round(k * step * RATE))
    style = s.get("style", "ambient")
    lead_voice = bell if style in ("ambient", "drone", "chime") else epiano

    toks = parse_melody(s.get("melody", ""))
    i = 0
    while i < len(toks):
        j = i + 1
        while j < len(toks) and toks[j] == "-":
            j += 1
        if toks[i] not in ("-", "."):
            a = sx(2 * i)
            b = min(a + max(sx(2 * (j - i)), int(1.2 * RATE)), total + tail)  # let it ring past its length
            mel[a:b] += lead_voice(note_hz(toks[i]), b - a)
        i = j

    for bar, sym in enumerate(chords):
        root, ivs = chord_notes(sym)
        tones = [root + iv for iv in ivs]
        base = bar * bar_n
        if style in ("ambient", "chime"):
            for m in tones:
                chordal[base:base + bar_n + sx(4)] += pad(midi_hz(m + 12), bar_n + sx(4)) * 0.6
            low[base:base + bar_n] += bass(midi_hz(root - 12), bar_n) * 0.8
        if style == "chime":
            seq = tones + [tones[0] + 12]
            for k in range(0, 16, 2):
                a = base + sx(k)
                n = min(sx(6), total + tail - a)
                chordal[a:a + n] += bell(midi_hz(seq[(k // 2) % len(seq)] + 24), n) * 0.5
        if style == "ostinato":
            order = [0, 2, 1, 2, 0, 2, 1, 2]  # root, fifth, third, fifth...
            for k in range(8):
                m = tones[order[k] % len(tones)] + 12
                a = base + sx(2 * k)
                n = min(sx(4), total + tail - a)
                chordal[a:a + n] += epiano(midi_hz(m), n) * 0.55
            for k in (0, 8):
                a = base + sx(k)
                n = min(sx(8), total + tail - a)
                low[a:a + n] += bass(midi_hz(root - 12), n)
            chordal[base:base + bar_n] += pad(midi_hz(tones[0] + 12), bar_n) * 0.25
        if style == "drone":
            for m in (root - 12, root - 5):
                low[base:base + bar_n + sx(4)] += pad(midi_hz(m), bar_n + sx(4)) * 0.9
        pattern = s.get("drums", "")
        for k, ch in enumerate(pattern):
            if ch != ".":
                a = base + sx(k)
                n = min(int(0.3 * RATE), total + tail - a)
                drums[a:a + n] += drum(ch, n, rng)

    left = 0.30 * mel + 0.26 * chordal * 0.9 + 0.34 * low + 0.22 * drums
    right = 0.30 * mel * 0.9 + 0.26 * chordal * 1.1 + 0.34 * low + 0.22 * drums
    pcm = echo(np.stack([left, right], axis=1))
    if s.get("loop", True):  # wrap the tail onto the start, so the loop is seamless
        body = pcm[:total].copy()
        body[:tail] += pcm[total:total + tail]
        pcm = body
        out_n, in_n = int(0.008 * RATE), int(0.002 * RATE)  # no click where it wraps
        pcm[-out_n:] *= np.linspace(1, 0, out_n)[:, None]
        pcm[:in_n] *= np.linspace(0, 1, in_n)[:, None]
    else:  # a jingle rings out and fades
        pcm[-int(0.6 * RATE):] *= np.linspace(1, 0, int(0.6 * RATE))[:, None]
    pcm *= 12000 / max(1e-9, np.abs(pcm).max())  # the level of the built-in songs, under the 2600's effects
    return pcm.astype(np.int16)


def main():
    import json
    import wave
    from engine import paths
    with open(sys.argv[1]) as f:
        songs = json.load(f)["songs"]
    out = os.path.join(paths.SHOTS, "music")
    os.makedirs(out, exist_ok=True)
    for name, song in songs.items():
        if len(sys.argv) > 2 and name not in sys.argv[2:]:
            continue
        pcm = render(song)
        if song.get("loop", True):
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
