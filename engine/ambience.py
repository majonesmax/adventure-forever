"""The world's ambience: what you hear when the music is off (M) - a bright summer day in the meadow, birds
and a woodpecker in the woods, still air in the castle halls, drips in the catacombs.

A world chooses a sound for each of its places in pack.json ("ambience": {place: sound}, content/world.py);
a world that chooses none is silent. The sounds (SOUNDS) are a bed that loops - the air - and calls dropped in
at random moments, each placed somewhere left or right, so it never repeats the same way twice.

The ambience only plays while the music is off: under music, a bed of noise only muddies it. It fades in and
out, and from place to place. engine/nature.py makes the sounds.

Usage: python -m engine.ambience     -> shots/ambience/: 30 seconds of each sound, to listen to
"""

import os
import threading
import wave
from typing import Any, Callable

import numpy as np

from engine import nature as N
from engine.nature import RATE, seconds
from shared.types import Floats, Samples

FPS = 60                 # the game's frames a second (the calls are timed in frames)
BED_LEVEL = 450          # a bed's average loudness: a background
BED_PEAK = 3000          # ...its loudest moments rounded off towards this
CALL_LEVEL = 1700        # a call's average loudness while it sounds
CALL_PEAK = 12000        # ...its loudest moments rounded off towards this
FADE_SECONDS = 2.0       # in and out as the music stops and starts, and between places
VARIANTS = 6             # differently made versions of each call


def summer() -> Floats:
    return N.breeze(1) + 0.35 * N.leaves(2)


def woods() -> Floats:
    return 0.7 * N.breeze(3) + 0.6 * N.leaves(4)


def frost() -> Floats:
    return N.breeze(5, calm=0.5) + 0.1 * N.band(N.noise(seconds(N.LOOP_SECONDS), 6), 600, 0.3)


Recipe = tuple[Callable[[], Floats], dict[str, tuple[int, float]], tuple[float, float]]
Voice = list[Any]        # [samples, position, pan at the start, pan at the end]; position moves as it plays
SOUNDS: dict[str, Recipe] = {   # name: (the bed, {call: (how often, how loud)}, seconds between calls)
    "summer": (summer, {"chirps": (4, 1.0), "two_notes": (3, 0.8), "trill": (2, 0.7), "coo": (1, 0.6),
                        "bee": (1, 0.35)}, (1.5, 5.0)),
    "woods": (woods, {"chirps": (3, 1.0), "trill": (3, 0.8), "two_notes": (1, 0.7),
                      "woodpecker": (1, 0.6)}, (1.0, 4.0)),
    "hall": (lambda: N.still_air(7), {"chirps": (1, 0.3), "two_notes": (1, 0.25)}, (6.0, 14.0)),
    "cave": (lambda: N.still_air(8, 40, 300), {"drip": (1, 0.6)}, (1.5, 6.0)),
    "embers": (lambda: N.embers(9), {"pop": (1, 0.5)}, (1.0, 4.0)),
    "frost": (frost, {"chirps": (1, 0.5)}, (8.0, 16.0)),
}
MOVING = {"bee"}         # calls that cross from one side to the other as they sound


def bed_pcm(track: Floats) -> Samples:
    """To int16 at BED_LEVEL on average, peaks rounded off below BED_PEAK."""
    average = np.sqrt((track ** 2).mean())
    scaled = track / max(1e-9, average) * BED_LEVEL
    return (BED_PEAK * np.tanh(scaled / BED_PEAK)).astype(np.int16)


def call_samples(sound: Floats, loudness: float) -> Floats:
    """A mono call at CALL_LEVEL x loudness on average while it sounds (its quiet tail not counted), peaks
    rounded off below CALL_PEAK; float32, to be panned as it plays."""
    sounding = sound[np.abs(sound) > np.abs(sound).max() * 0.1]
    average = np.sqrt((sounding ** 2).mean())
    scaled = sound / max(1e-9, average) * CALL_LEVEL * loudness
    return (CALL_PEAK * np.tanh(scaled / CALL_PEAK)).astype(np.float32)


class Sound:
    """One of SOUNDS, made: its bed (int16 stereo) and its calls (float32 mono), and how to pick a call."""

    def __init__(self, name: str):
        make_bed, calls, self.gap = SOUNDS[name]
        self.bed: Samples = bed_pcm(make_bed())
        self.calls: list[tuple[str, Floats]] = []
        weights: list[int] = []
        for call, (often, loud) in calls.items():
            for seed in range(VARIANTS):
                self.calls.append((call, call_samples(N.CALLS[call](seed), loud)))
                weights.append(often)
        self.weights = np.array(weights, float) / sum(weights)

    def frames_to_next_call(self, rng: np.random.Generator) -> int:
        return int(rng.uniform(*self.gap) * FPS)


class Ambience:
    """Plays the world's sounds. follow() once a frame from the game loop; render() from the sound card's
    callback. Each sound is made the first time it's needed, in the background (about a second)."""

    def __init__(self) -> None:
        self.sounds: dict[str, Sound] = {}
        self.making: set[str] = set()
        self.name: str | None = None          # the sound playing now...
        self.leaving: str | None = None       # ...and the one fading out under it
        self.crossfade = 0
        self.positions: dict[str, int] = {}   # each bed's place in its loop
        self.quiet, self.gain = False, 0.0
        self.voices: list[Voice] = []         # each call playing
        self.rng = np.random.default_rng()
        self.until_call = FPS
        self.lock = threading.Lock()

    # --- following the game ---
    def follow(self, name: str | None, quiet: bool) -> None:
        """Once a frame. name: the sound for where the game is (None: silence); quiet: no music playing."""
        self.quiet = quiet and name is not None
        if name is not None and name not in self.sounds:
            self.make(name)
        if name != self.name:
            with self.lock:
                self.name, self.leaving, self.crossfade = name, self.name, seconds(FADE_SECONDS)
        self.count_down_to_call()

    def make(self, name: str) -> None:
        if name in self.making:
            return
        self.making.add(name)

        def work() -> None:
            self.sounds[name] = Sound(name)
        threading.Thread(target=work, daemon=True).start()

    def count_down_to_call(self) -> None:
        sound = self.sounds.get(self.name) if self.name is not None else None
        if not self.quiet or sound is None:
            return
        self.until_call -= 1
        if self.until_call > 0:
            return
        self.until_call = sound.frames_to_next_call(self.rng)
        call, samples = sound.calls[self.rng.choice(len(sound.calls), p=sound.weights)]
        pan = self.rng.uniform(-0.8, 0.8)
        end = -pan if call in MOVING else pan
        with self.lock:
            self.voices.append([samples, 0, pan, end])

    def add(self, samples: Floats, pan: float) -> None:
        """Play a sound once (mono float32, from call_samples), placed at `pan` (-1 left to 1 right)."""
        with self.lock:
            self.voices.append([samples, 0, pan, pan])

    # --- the sound card's callback ---
    def render(self, count: int) -> Samples:
        """The next `count` stereo samples: the bed, as loud as the quiet allows, and the calls."""
        with self.lock:
            out = self.bed(count) * self.fade_gain(count)[:, None]
            for voice in self.voices:
                out += self.take_call(voice, count)
            self.voices = [voice for voice in self.voices if voice[1] < len(voice[0])]
        return np.clip(out, -32767, 32767).astype(np.int16)

    def take_call(self, voice: Voice, count: int) -> Floats:
        samples, position, start_pan, end_pan = voice
        take = min(count, len(samples) - position)
        along = (position + np.arange(take)) / len(samples)
        pan = start_pan + (end_pan - start_pan) * along
        out = np.zeros((count, 2), np.float32)
        out[:take, 0] = samples[position:position + take] * (1 - pan) / 2
        out[:take, 1] = samples[position:position + take] * (1 + pan) / 2
        voice[1] = position + take
        return out

    def fade_gain(self, count: int) -> Floats:
        """The beds' loudness through these samples, moving towards full when quiet, none when not."""
        target = 1.0 if self.quiet else 0.0
        most = count / seconds(FADE_SECONDS)
        start, self.gain = self.gain, self.gain + float(np.clip(target - self.gain, -most, most))
        return np.linspace(start, self.gain, count)

    def bed(self, count: int) -> Floats:
        out = self.take_bed(self.name, count).astype(np.float32)
        if self.crossfade:
            done = seconds(FADE_SECONDS) - self.crossfade + np.arange(count)
            fade_in = np.clip(done / seconds(FADE_SECONDS), 0, 1)[:, None]
            out = out * fade_in + self.take_bed(self.leaving, count) * (1 - fade_in)
            self.crossfade = max(0, self.crossfade - count)
        return out

    def take_bed(self, name: str | None, count: int) -> Samples:
        """`count` samples of a sound's bed from where it left off; silence if it isn't made yet."""
        if name is None or name not in self.sounds:
            return np.zeros((count, 2), np.int16)
        sound = self.sounds[name]
        start = self.positions.get(name, 0)
        self.positions[name] = (start + count) % len(sound.bed)
        return sound.bed[(start + np.arange(count)) % len(sound.bed)]


def listen(name: str, length_seconds: int = 30) -> Samples:
    """`length_seconds` of a sound as the game plays it, to listen to."""
    ambience = Ambience()
    ambience.sounds[name] = Sound(name)
    ambience.gain = 1.0
    block = RATE // FPS
    out = []
    for _frame in range(length_seconds * FPS):
        ambience.follow(name, quiet=True)
        out.append(ambience.render(block))
    return np.concatenate(out)


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    folder = os.path.join(root, "shots", "ambience")
    os.makedirs(folder, exist_ok=True)
    for name in SOUNDS:
        pcm = listen(name)
        path = os.path.join(folder, f"{name}.wav")
        with wave.open(path, "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(pcm.tobytes())
        print(f"{path}  {len(pcm) / RATE:.0f} s")


if __name__ == "__main__":
    main()
