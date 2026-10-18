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

import numpy as np

from engine import nature as N
from engine.nature import RATE, seconds

FPS = 60                 # the game's frames a second (the calls are timed in frames)
BED_LEVEL = 450          # a bed's average loudness: a background
BED_PEAK = 3000          # ...its loudest moments rounded off towards this
CALL_LEVEL = 1700        # a call's average loudness while it sounds
CALL_PEAK = 12000        # ...its loudest moments rounded off towards this
FADE_SECONDS = 2.0       # in and out as the music stops and starts, and between places
VARIANTS = 6             # differently made versions of each call


def summer():
    return N.breeze(1) + 0.35 * N.leaves(2)


def woods():
    return 0.7 * N.breeze(3) + 0.6 * N.leaves(4)


def frost():
    return N.breeze(5, calm=0.5) + 0.1 * N.band(N.noise(seconds(N.LOOP_SECONDS), 6), 600, 0.3)


SOUNDS = {   # name: (the bed, {call: (how often, how loud)}, seconds between calls)
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


def bed_pcm(track):
    """To int16 at BED_LEVEL on average, peaks rounded off below BED_PEAK."""
    average = np.sqrt((track ** 2).mean())
    scaled = track / max(1e-9, average) * BED_LEVEL
    return (BED_PEAK * np.tanh(scaled / BED_PEAK)).astype(np.int16)


def call_samples(sound, loudness):
    """A mono call at CALL_LEVEL x loudness on average while it sounds (its quiet tail not counted), peaks
    rounded off below CALL_PEAK; float32, to be panned as it plays."""
    sounding = sound[np.abs(sound) > np.abs(sound).max() * 0.1]
    average = np.sqrt((sounding ** 2).mean())
    scaled = sound / max(1e-9, average) * CALL_LEVEL * loudness
    return (CALL_PEAK * np.tanh(scaled / CALL_PEAK)).astype(np.float32)


class Sound:
    """One of SOUNDS, made: its bed (int16 stereo) and its calls (float32 mono), and how to pick a call."""

    def __init__(self, name):
        make_bed, calls, self.gap = SOUNDS[name]
        self.bed = bed_pcm(make_bed())
        self.calls, weights = [], []
        for call, (often, loud) in calls.items():
            for seed in range(VARIANTS):
                self.calls.append((call, call_samples(N.CALLS[call](seed), loud)))
                weights.append(often)
        self.weights = np.array(weights, float) / sum(weights)

    def frames_to_next_call(self, rng):
        return int(rng.uniform(*self.gap) * FPS)


class Ambience:
    """Plays the world's sounds. follow() once a frame from the game loop; render() from the sound card's
    callback. Each sound is made the first time it's needed, in the background (about a second)."""

    def __init__(self):
        self.sounds, self.making = {}, set()
        self.name, self.leaving, self.crossfade = None, None, 0
        self.positions = {}
        self.quiet, self.gain = False, 0.0
        self.voices = []          # [samples, position, pan at the start, pan at the end] of each call playing
        self.rng = np.random.default_rng()
        self.until_call = FPS
        self.lock = threading.Lock()

    # --- following the game ---
    def follow(self, name, quiet):
        """Once a frame. name: the sound for where the game is (None: silence); quiet: no music playing."""
        self.quiet = quiet and name is not None
        if name is not None and name not in self.sounds:
            self.make(name)
        if name != self.name:
            with self.lock:
                self.name, self.leaving, self.crossfade = name, self.name, seconds(FADE_SECONDS)
        self.count_down_to_call()

    def make(self, name):
        if name in self.making:
            return
        self.making.add(name)

        def work():
            self.sounds[name] = Sound(name)
        threading.Thread(target=work, daemon=True).start()

    def count_down_to_call(self):
        sound = self.sounds.get(self.name)
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

    # --- the sound card's callback ---
    def render(self, count):
        """The next `count` stereo samples: the bed, as loud as the quiet allows, and the calls."""
        with self.lock:
            out = self.bed(count) * self.fade_gain(count)[:, None]
            for voice in self.voices:
                out += self.take_call(voice, count)
            self.voices = [voice for voice in self.voices if voice[1] < len(voice[0])]
        return np.clip(out, -32767, 32767).astype(np.int16)

    def take_call(self, voice, count):
        samples, position, start_pan, end_pan = voice
        take = min(count, len(samples) - position)
        along = (position + np.arange(take)) / len(samples)
        pan = start_pan + (end_pan - start_pan) * along
        out = np.zeros((count, 2), np.float32)
        out[:take, 0] = samples[position:position + take] * (1 - pan) / 2
        out[:take, 1] = samples[position:position + take] * (1 + pan) / 2
        voice[1] = position + take
        return out

    def fade_gain(self, count):
        """The beds' loudness through these samples, moving towards full when quiet, none when not."""
        target = 1.0 if self.quiet else 0.0
        most = count / seconds(FADE_SECONDS)
        start, self.gain = self.gain, self.gain + float(np.clip(target - self.gain, -most, most))
        return np.linspace(start, self.gain, count)

    def bed(self, count):
        out = self.take_bed(self.name, count).astype(np.float32)
        if self.crossfade:
            done = seconds(FADE_SECONDS) - self.crossfade + np.arange(count)
            fade_in = np.clip(done / seconds(FADE_SECONDS), 0, 1)[:, None]
            out = out * fade_in + self.take_bed(self.leaving, count) * (1 - fade_in)
            self.crossfade = max(0, self.crossfade - count)
        return out

    def take_bed(self, name, count):
        """`count` samples of a sound's bed from where it left off; silence if it isn't made yet."""
        sound = self.sounds.get(name)
        if sound is None:
            return np.zeros((count, 2), np.int16)
        start = self.positions.get(name, 0)
        self.positions[name] = (start + count) % len(sound.bed)
        return sound.bed[(start + np.arange(count)) % len(sound.bed)]


def listen(name, length_seconds=30):
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


def main():
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
