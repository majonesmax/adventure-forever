"""The remastered sound effects: the 2600's six sounds - pick up, drop, a dragon's roar, eaten, a dragon dies,
the win - played as the look on screen would play them, each dragon in its own voice; and two the 2600
never had, a castle gate opening and closing. Each look has its own set (nes.py: chip blips;
snes.py: bells and a growl with echo; vga.py: PC FM; paper.py: a toy xylophone, a kazoo, a slide whistle).

The game says when: it starts a sound by setting a counter in RAM (engine/ram_map.py: SOUND_COUNTER, with
SOUND_TYPE saying which) - heard() reads that, even when a sound cuts off the one before. While the
remastered effects play, the 2600's own are held back (app/window.py); in the 2600-only view, the 2600's
play instead.

Usage: python -m engine.effects     -> shots/effects/<look>_<sound>.wav, to listen to
"""

import os
import threading
import wave

import numpy as np

from engine import ram_map as M
from engine.chiptune import RATE
from engine.effects import nes, paper, snes, vga
from engine.effects.tools import DRAGON_VOICES, KINDS, Voice

SETS = {"nes": nes.EFFECTS, "snes": snes.EFFECTS, "vga": vga.EFFECTS, "paper": paper.EFFECTS}
GAME_SOUNDS = {0: "win", 1: "roar", 2: "eaten", 3: "dragon_dies", 4: "drop", 5: "pickup"}   # SOUND_TYPE
DRAGON_SOUNDS = ("roar", "dragon_dies")   # each dragon has its own voice (tools.DRAGON_VOICES)
DRAGONS = {M.RED_DRAGON: "red", M.YELLOW_DRAGON: "yellow", M.GREEN_DRAGON: "green"}
LEVEL = 4200             # an effect's average loudness while it sounds: a little above the music's
PEAK = 15000             # ...its loudest moments rounded off towards this
SHARE = {"drop": 0.7, "pickup": 0.85, "gate_open": 0.8, "gate_close": 0.8}   # quieter than the dragons
FALLBACK = "nes"         # a look without its own set (the template) uses the NES's


def heard(before, after):
    """The sounds that start between two frames' RAM (128 bytes each, from $80): the game's own (a roar or
    a death named for its dragon: "roar_red"), and a gate starting to open or close."""
    def byte(ram, address):
        return int(ram[address - 0x80])
    sounds = []
    if byte(after, M.SOUND_COUNTER) > byte(before, M.SOUND_COUNTER):   # it only counts down, unless a
        name = GAME_SOUNDS.get(byte(after, M.SOUND_TYPE))              # sound (re)starts it
        if name in DRAGON_SOUNDS:
            name = f"{name}_{which_dragon(before, after, name)}"
        if name:
            sounds.append(name)
    for gate in M.PORTCULLIS:
        if byte(before, gate) == M.GATE_SHUT and byte(after, gate) != M.GATE_SHUT:
            sounds.append("gate_open")
        if byte(before, gate) == M.GATE_UP and byte(after, gate) not in (M.GATE_UP, M.GATE_SHUT):
            sounds.append("gate_close")
    return sounds


def which_dragon(before, after, sound):
    """The dragon a roar or a death belongs to: the one whose state just changed to roaring (anything but 0
    normal, 1 dead, 2 has eaten) or to dead - else any dragon in that state; else Yorgle."""
    def state(ram, dragon):
        return int(ram[dragon + M.DRAGON_STATE_OFFSET - 0x80])
    def fits(value):
        return value == 1 if sound == "dragon_dies" else value not in (0, 1, 2)
    changed = [colour for dragon, colour in DRAGONS.items()
               if state(before, dragon) != state(after, dragon) and fits(state(after, dragon))]
    either = changed or [colour for dragon, colour in DRAGONS.items() if fits(state(after, dragon))]
    return either[0] if either else "yellow"


def to_pcm(track, name):
    """A mono effect -> int16 stereo at LEVEL (x its SHARE) on average while it sounds - so a pure whistle
    and a noisy crash come out alike - with its peaks rounded off below PEAK."""
    sounding = track[np.abs(track) > np.abs(track).max() * 0.1]
    average = np.sqrt((sounding ** 2).mean())
    scaled = track / max(1e-9, average) * LEVEL * SHARE.get(name, 1.0)
    rounded = PEAK * np.tanh(scaled / PEAK)
    return np.repeat(rounded[:, None], 2, axis=1).astype(np.int16)


def made(effects):
    """(name, sound) for each of a look's effects - the dragons' in every kind of voice, for each dragon."""
    for name, make in effects.items():
        if name in DRAGON_SOUNDS:
            for kind in KINDS:
                for colour, (pitch, length) in DRAGON_VOICES.items():
                    yield f"{name}_{kind}_{colour}", to_pcm(make(Voice(kind, pitch, length)), name)
        else:
            yield name, to_pcm(make(), name)


class Effects:
    """Plays the effects. play() from the game loop; render() from the sound card's callback. Every set is
    made in the background at the start (a fraction of a second); until then, nothing plays."""

    def __init__(self):
        self.sets = {}
        self.voices = []          # [samples, position] of each effect playing
        self.lock = threading.Lock()
        threading.Thread(target=self.make_all, daemon=True).start()

    def make_all(self):
        for look, effects in SETS.items():
            self.sets[look] = dict(made(effects))

    def play(self, name, look, voices):
        """Start one of the game's sounds, as `look` (a look's platform: nes, snes...) plays it. voices: the
        cast's kind of voice for each dragon colour (a roar_red becomes roar_squawk_red, say)."""
        effects = self.sets.get(look if look in SETS else FALLBACK)
        if effects is None:
            return
        sound, _, colour = name.rpartition("_")
        if sound in DRAGON_SOUNDS:
            name = f"{sound}_{voices.get(colour, 'growl')}_{colour}"
        with self.lock:
            self.voices.append([effects[name], 0])

    def render(self, count):
        """The next `count` stereo samples of every effect playing."""
        out = np.zeros((count, 2), np.float32)
        with self.lock:
            for voice in self.voices:
                samples, position = voice
                take = min(count, len(samples) - position)
                out[:take] += samples[position:position + take]
                voice[1] = position + take
            self.voices = [voice for voice in self.voices if voice[1] < len(voice[0])]
        return np.clip(out, -32767, 32767).astype(np.int16)


def main():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    folder = os.path.join(root, "shots", "effects")
    os.makedirs(folder, exist_ok=True)
    for look, effects in SETS.items():
        sounds = dict(made(effects))
        for name, pcm in sounds.items():
            path = os.path.join(folder, f"{look}_{name}.wav")
            with wave.open(path, "wb") as out:
                out.setnchannels(2)
                out.setsampwidth(2)
                out.setframerate(RATE)
                out.writeframes(pcm.tobytes())
        print(f"{folder}/{look}_*.wav  ({len(sounds)} sounds)")

