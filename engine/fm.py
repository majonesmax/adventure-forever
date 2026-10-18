"""An FM synth for songs in the early-90s PC sound (an AdLib card's two-operator FM): soft electric piano,
glassy bells, warm pads, round bass, quiet drums - and an echo, for empty rooms.

Songs use chiptune.py's notation - a tempo, one chord per bar, a melody in eighth notes ("-" holds, "."
rests), 16 drum steps per bar (k kick, s snare, h hi-hat, . nothing) - with these arrangement styles:
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
from engine.chiptune import RATE, Timing, chord_notes, midi_hz, note_hz, parse_melody  # noqa: E402


def env(length, attack=0.005, decay=0.6, sustain=0.0, release=0.05):
    """A note's loudness over time: a rise, a fall towards `sustain`, a fade at the end."""
    seconds = np.arange(length) / RATE
    after_attack = sustain + (1 - sustain) * np.exp(-(seconds - attack) / decay)
    loudness = np.where(seconds < attack, seconds / max(attack, 1e-6), after_attack)
    release_n = min(length, int(release * RATE))
    if release_n:
        loudness[-release_n:] *= np.linspace(1, 0, release_n)
    return loudness


def fm(freq, length, ratio=1.0, index=1.0, index_decay=None, detune=0.0):
    """Two-operator FM: a sine carrier, phase-modulated by a sine at freq * ratio, the modulation `index`
    fading over index_decay seconds (None: steady) - bright at the attack, mellow as it rings."""
    seconds = np.arange(length) / RATE
    carrier = freq * (1 + detune)
    depth = index * (np.exp(-seconds / index_decay) if index_decay else 1.0)
    modulator = np.sin(2 * np.pi * carrier * ratio * seconds)
    return np.sin(2 * np.pi * carrier * seconds + depth * modulator)


def epiano(freq, length):
    tine = 0.15 * fm(freq, length, ratio=14.0, index=1.2, index_decay=0.02)  # the bright "tink" on top
    body = fm(freq, length, ratio=1.0, index=1.8, index_decay=0.35)
    return (body + tine) * env(length, decay=1.1, sustain=0.15)


def bell(freq, length):
    return fm(freq, length, ratio=3.5, index=2.2, index_decay=0.9) * env(length, decay=2.4, release=0.2)


def pad(freq, length):
    lower = fm(freq, length, ratio=1.0, index=0.7, detune=-0.003)  # two voices a hair apart: warmth
    upper = fm(freq, length, ratio=2.0, index=0.4, detune=0.003)
    return 0.5 * (lower + upper) * env(length, attack=0.7, decay=3.0, sustain=0.8, release=0.5)


def bass(freq, length):
    tone = fm(freq, length, ratio=1.0, index=1.4, index_decay=0.18)
    return tone * env(length, decay=0.9, sustain=0.45, release=0.04)


def drum(kind, length, rng):
    seconds = np.arange(length) / RATE
    if kind == "k":  # a soft, low thump
        freqs = 46 + 70 * np.exp(-seconds / 0.04)
        return np.sin(2 * np.pi * np.cumsum(freqs) / RATE) * np.exp(-seconds / 0.16)
    noise = rng.uniform(-1, 1, length)
    if kind == "s":
        return np.convolve(noise, np.ones(3) / 3, "same") * np.exp(-seconds / 0.09) * 0.35
    if kind == "h":
        return np.diff(noise, prepend=0) * np.exp(-seconds / 0.02) * 0.12
    return np.zeros(length)


def echo(pcm, seconds=0.33, feedback=0.38, mix=0.32):
    """A feedback delay, for the empty-office reverb (pcm: (n, 2)) - 5 repeats, each quieter."""
    delay = int(seconds * RATE)
    out = pcm.copy()
    for repeat in range(1, 6):
        if delay * repeat >= len(pcm):
            break
        out[delay * repeat:] += pcm[:-delay * repeat] * (feedback ** repeat) * mix
    return out


def render(song):
    """A song dict -> int16 stereo PCM of one pass (loops cleanly: the echo's tail wraps round to the
    start)."""
    timing = Timing(song)
    chords = song["chords"].split()
    total = len(chords) * timing.bar_n
    length = total + int(3.0 * RATE)  # room for notes and the echo to ring past the end
    melody, chordal, low, drums = (np.zeros(length) for _ in range(4))
    rng = np.random.default_rng(11)
    style = song.get("style", "ambient")
    lead_voice = bell if style in ("ambient", "drone", "chime") else epiano
    add_melody(melody, parse_melody(song.get("melody", "")), lead_voice, timing, length)
    for bar, symbol in enumerate(chords):
        root, intervals = chord_notes(symbol)
        tones = [root + interval for interval in intervals]
        start = bar * timing.bar_n
        if style in ("ambient", "chime"):
            add_pad_and_bass(chordal, low, root, tones, start, timing)
        if style == "chime":
            add_bell_arpeggio(chordal, tones, start, timing, length)
        if style == "ostinato":
            add_ostinato(chordal, low, root, tones, start, timing, length)
        if style == "drone":
            add_drone(low, root, start, timing)
        add_drums(drums, song.get("drums", ""), start, timing, length, rng)
    return mix_down(melody, chordal, low, drums, total, song.get("loop", True))


def add_melody(melody, tokens, voice, timing, length):
    """The lead: eighth-note tokens ("-" holds, "." rests); each note rings at least 1.2 s."""
    i = 0
    while i < len(tokens):
        j = i + 1
        while j < len(tokens) and tokens[j] == "-":
            j += 1
        if tokens[i] not in ("-", "."):
            start = timing.at(2 * i)
            end = min(start + max(timing.at(2 * (j - i)), int(1.2 * RATE)), length)
            melody[start:end] += voice(note_hz(tokens[i]), end - start)
        i = j


def add_pad_and_bass(chordal, low, root, tones, bar_start, timing):
    """ambient / chime: a pad holds the chord (a little past the bar), a soft bass under it."""
    held = timing.bar_n + timing.at(4)
    for midi in tones:
        chordal[bar_start:bar_start + held] += pad(midi_hz(midi + 12), held) * 0.6
    low[bar_start:bar_start + timing.bar_n] += bass(midi_hz(root - 12), timing.bar_n) * 0.8


def add_bell_arpeggio(chordal, tones, bar_start, timing, length):
    """chime: bells arpeggiate the chord, two octaves up, in eighths."""
    sequence = tones + [tones[0] + 12]
    for sixteenth in range(0, 16, 2):
        start = bar_start + timing.at(sixteenth)
        ring = min(timing.at(6), length - start)
        midi = sequence[(sixteenth // 2) % len(sequence)] + 24
        chordal[start:start + ring] += bell(midi_hz(midi), ring) * 0.5


def add_ostinato(chordal, low, root, tones, bar_start, timing, length):
    """ostinato: an electric piano repeats the chord in eighths, bass on beats 1 and 3, a quiet pad."""
    order = [0, 2, 1, 2, 0, 2, 1, 2]  # root, fifth, third, fifth...
    for eighth in range(8):
        midi = tones[order[eighth] % len(tones)] + 12
        start = bar_start + timing.at(2 * eighth)
        ring = min(timing.at(4), length - start)
        chordal[start:start + ring] += epiano(midi_hz(midi), ring) * 0.55
    for sixteenth in (0, 8):
        start = bar_start + timing.at(sixteenth)
        ring = min(timing.at(8), length - start)
        low[start:start + ring] += bass(midi_hz(root - 12), ring)
    chordal[bar_start:bar_start + timing.bar_n] += pad(midi_hz(tones[0] + 12), timing.bar_n) * 0.25


def add_drone(low, root, bar_start, timing):
    """drone: a low pad on the chord's root and fifth."""
    held = timing.bar_n + timing.at(4)
    for midi in (root - 12, root - 5):
        low[bar_start:bar_start + held] += pad(midi_hz(midi), held) * 0.9


def add_drums(drums, pattern, bar_start, timing, length, rng):
    """One bar of the drum pattern (16 steps: k kick, s snare, h hi-hat, . nothing)."""
    for sixteenth, kind in enumerate(pattern):
        if kind == ".":
            continue
        start = bar_start + timing.at(sixteenth)
        ring = min(int(0.3 * RATE), length - start)
        drums[start:start + ring] += drum(kind, ring, rng)


def mix_down(melody, chordal, low, drums, total, loop):
    """The voices -> stereo with an echo; a loop's echo tail wraps onto its start, a jingle fades out."""
    left = 0.30 * melody + 0.26 * chordal * 0.9 + 0.34 * low + 0.22 * drums
    right = 0.30 * melody * 0.9 + 0.26 * chordal * 1.1 + 0.34 * low + 0.22 * drums
    pcm = echo(np.stack([left, right], axis=1))
    tail = len(pcm) - total
    if loop:  # wrap the tail onto the start, so the loop is seamless
        body = pcm[:total].copy()
        body[:tail] += pcm[total:total + tail]
        pcm = body
        fade_out, fade_in = int(0.008 * RATE), int(0.002 * RATE)  # no click where it wraps
        pcm[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
        pcm[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
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
