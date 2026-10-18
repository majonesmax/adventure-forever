"""Background music, one piece per AREA (title / overworld / dungeon / final / win), mixed under the 2600's
own sound effects in the sound card's callback.

Where each area's music comes from: the world on screen's own soundtrack if it has one (world/music.json -
content/world.py), then (first file found wins):
  private/music.json, music/music.json   {"title": {"nsf": "music/x.nsf", "track": 1},   an NSF via libgme
                                          "win": {"file": "music/win.wav"},              a WAV file
                                          "dungeon": {"song": "dungeon"}, ...}           a built-in song
  otherwise                               the built-in original chiptune songs (chiptune.py) - no files needed
NSF tracks are played by game-music-emu (libgme: macOS `brew install game-music-emu`, Linux your package
manager) through ctypes, opened at the emulator's sample rate (31440 Hz) so samples add straight onto the
2600's.

Usage: python music.py --survey FILE.nsf          # length + loudness of every track
       python music.py --play FILE.nsf N [secs]   # listen to track N (1-based)
       python music.py --audition FILE.nsf N...   # 10 s of each listed track
"""

import ctypes as C
import ctypes.util
import os
import sys

import numpy as np

from engine import paths

HERE = paths.ROOT
NSF = None  # no NSF by default - see the music config above
GME_FILE = {"macos": "libgme.dylib", "windows": "gme.dll", "linux": "libgme.so"}[paths.SYSTEM]
LIB_PATHS = [os.path.join(HERE, "lib", GME_FILE),                     # bundled with a personal app build
             "/opt/homebrew/lib/libgme.dylib", "/usr/local/lib/libgme.dylib"]  # Homebrew (macOS)
RATE = 31440


def _lib():
    found = [path for path in LIB_PATHS if os.path.exists(path)] or [ctypes.util.find_library("gme")]
    if not found[0]:
        raise OSError("libgme not found - install game-music-emu (macOS: brew install game-music-emu; "
                      "Linux: your package manager's libgme)")
    lib = C.CDLL(found[0])
    lib.gme_open_file.restype = C.c_char_p
    lib.gme_open_file.argtypes = [C.c_char_p, C.POINTER(C.c_void_p), C.c_int]  # (path, out, rate)
    lib.gme_track_count.argtypes = [C.c_void_p]
    lib.gme_start_track.restype = C.c_char_p
    lib.gme_start_track.argtypes = [C.c_void_p, C.c_int]
    lib.gme_play.restype = C.c_char_p
    lib.gme_play.argtypes = [C.c_void_p, C.c_int, C.POINTER(C.c_short)]
    lib.gme_track_ended.argtypes = [C.c_void_p]
    lib.gme_ignore_silence.argtypes = [C.c_void_p, C.c_int]
    lib.gme_tell.argtypes = [C.c_void_p]
    lib.gme_delete.argtypes = [C.c_void_p]
    return lib


class Music:
    """One NSF, one track at a time. render(n) -> n stereo frames (int16, shape (n, 2))."""

    def __init__(self, path=NSF, rate=RATE):
        self.lib = _lib()
        self.emu = C.c_void_p()
        err = self.lib.gme_open_file(path.encode(), C.byref(self.emu), rate)
        if err:
            raise RuntimeError(f"gme: {err.decode()}")
        self.lib.gme_ignore_silence(self.emu, 1)  # don't auto-end tracks on quiet passages
        self.tracks = self.lib.gme_track_count(self.emu)
        self.track = None

    def start(self, track):
        """track: 1-based like the NSF's own numbering."""
        err = self.lib.gme_start_track(self.emu, track - 1)
        if err:
            raise RuntimeError(f"gme: {err.decode()}")
        self.track = track

    def stop(self):
        self.track = None

    def render(self, frames):
        if self.track is None or frames <= 0:
            return np.zeros((max(frames, 0), 2), np.int16)
        buf = (C.c_short * (frames * 2))()
        self.lib.gme_play(self.emu, frames * 2, buf)
        return np.ctypeslib.as_array(buf).reshape(frames, 2).copy()

    def ended(self):
        return bool(self.lib.gme_track_ended(self.emu))


def survey(path, seconds=90):
    """Per NSF track: how long until it goes silent for good (music loops, jingles/SFX stop), and loudness."""
    music = Music(path)
    print(f"{music.tracks} tracks")
    for track in range(1, music.tracks + 1):
        music.start(track)
        audio = music.render(RATE * seconds).astype(float)
        env = np.abs(audio).mean(axis=1)
        block = RATE // 10
        levels = env[:len(env) // block * block].reshape(-1, block).mean(axis=1)
        active = np.nonzero(levels > 30)[0]
        length = (active.max() + 1) / 10 if active.size else 0.0
        loud = 20 * np.log10(np.sqrt((audio ** 2).mean()) + 1e-9)
        still_playing = length >= seconds - 1
        kind = f"music (still playing at {seconds}s)" if still_playing else f"{length:.1f}s then silent"
        print(f"  track {track:2d}: {kind:32s} level {loud:5.1f} dB")


def play(path, track, secs=20):
    import sounddevice as sd
    music = Music(path)
    music.start(track)
    sd.play(music.render(RATE * secs), RATE, blocking=True)


CONFIGS = [os.path.join(HERE, "private", "music.json"), os.path.join(HERE, "music", "music.json")]
AREAS = ("title", "overworld", "dungeon", "final", "win")
FINAL_ROOMS = {0x13, 0x14, 0x15, 0x16, 0x1B}  # black maze + black castle interior: the "last dungeon"


BUILT_IN = {area: {"song": area} for area in AREAS}


def load_configs():
    """[(name, area -> source spec)]: every config file found, then the built-in songs (always there)."""
    import json
    found = []
    for path in CONFIGS:
        if os.path.exists(path):
            with open(path) as f:
                config = {area: source for area, source in json.load(f).items() if not area.startswith("_")}
                found.append((os.path.relpath(path, HERE), config))
    return found + [("built-in songs", BUILT_IN)]


class Pcm:
    """A rendered piece (built-in song or WAV file) played from memory; loops unless it's a jingle."""

    def __init__(self, pcm, loop):
        self.pcm, self.loop, self.pos = pcm, loop, 0

    def render(self, frames):
        out = np.zeros((frames, 2), np.int16)
        done = 0
        while done < frames:
            if self.pos >= len(self.pcm):
                if not self.loop:
                    break
                self.pos = 0
            count = min(frames - done, len(self.pcm) - self.pos)
            out[done:done + count] = self.pcm[self.pos:self.pos + count]
            done, self.pos = done + count, self.pos + count
        return out


def read_wav(path, rate):
    """16-bit WAV -> int16 stereo at `rate` (linear resampling if needed)."""
    import wave
    with wave.open(path) as w:
        channels, file_rate = w.getnchannels(), w.getframerate()
        samples = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, channels)
    samples = samples[:, :2] if channels >= 2 else np.repeat(samples, 2, axis=1)  # mono -> both sides
    if file_rate != rate:
        positions = np.arange(int(len(samples) * rate / file_rate)) * file_rate / rate
        resampled = [np.interp(positions, np.arange(len(samples)), samples[:, side]) for side in range(2)]
        samples = np.stack(resampled, axis=1).astype(np.int16)
    return samples


DARK, RED = 0x08, 0x36  # room colours: the dark rooms, and the red maze + castle interiors


def area_for(state):
    """Which music area this moment belongs to: title / overworld / dungeon / final / win."""
    if state.won:
        return "win"
    if state.on_title_screen:
        return "title"
    if state.room_num in FINAL_ROOMS:
        return "final"
    if state.room["colour"] in (DARK, RED):  # catacombs and black maze (dark), red maze, castle interiors
        return "dungeon"
    return "overworld"


def mix(sfx, mus, gain=1.0):
    """2600 sound effects + NES music, both at their original levels (music scaled only by the user's
    volume). Added in float; a soft knee above 28000 rounds off the rare peaks where both are loud at once
    instead of hard-clipping (the effects alone peak at ~22000, the music at ~13000)."""
    count = min(len(sfx), len(mus))
    mixed = sfx[:count].astype(np.float32) + gain * mus[:count].astype(np.float32)
    knee, top = 28000.0, 32767.0
    over = np.abs(mixed) > knee
    if over.any():
        above = np.abs(mixed[over]) - knee
        mixed[over] = np.sign(mixed[over]) * (knee + (top - knee) * np.tanh(above / (top - knee)))
    return mixed.astype(np.int16)


class MusicPlayer:
    """The music side of the mix, run from the sound card's callback (engine/emulator.py:
    AudioOut(mixer=...)).
    The game loop only says WHICH AREA to play (start/stop/on/gain/paused); the callback decides how much."""

    def __init__(self, rate=RATE, public=False):
        import threading
        self.rate, self.lock = rate, threading.Lock()
        self.on, self.gain, self.paused = True, 1.0, False
        # the first source found plays; next_source() cycles. public: only the built-in songs
        self.base = [("built-in songs", BUILT_IN)] if public else load_configs()
        self.configs, self.world = list(self.base), None
        self.which = 0
        self.current, self.nsf, self.cache = None, {}, {}

    @property
    def config(self):
        return self.configs[self.which][1]

    @property
    def source_name(self):
        return self.configs[self.which][0]

    def next_source(self):
        self.which = (self.which + 1) % len(self.configs)
        return self.source_name

    def use_world(self, world):
        """The world on screen: its soundtrack (if any) goes first and plays; N still cycles past it."""
        if world is self.world:
            return
        self.world = world
        own = []
        if world is not None and world.music:
            synth, songs = world.music.get("synth", "chiptune"), world.music["songs"]
            own = [(f"{world.name} soundtrack", {area: {"world_song": songs[name], "synth": synth}
                                                 for area, name in world.music["areas"].items()})]
        self.configs, self.which = own + self.base, 0

    def has(self, area):
        return area in self.config

    def _source(self, area):
        spec = self.config[area]
        if "world_song" in spec:  # a world's own song, rendered by its synth
            from engine import chiptune, fm
            key = (spec["synth"], id(spec["world_song"]))
            if key not in self.cache:
                self.cache[key] = (fm if spec["synth"] == "fm" else chiptune).render(spec["world_song"])
            return Pcm(self.cache[key], spec["world_song"].get("loop", True))
        if "song" in spec:
            from engine import chiptune
            if spec["song"] not in self.cache:
                self.cache[spec["song"]] = chiptune.render(spec["song"])
            return Pcm(self.cache[spec["song"]], chiptune.SONGS[spec["song"]]["loop"])
        if "file" in spec:
            path = os.path.join(HERE, spec["file"])
            if path not in self.cache:
                self.cache[path] = read_wav(path, self.rate)
            return Pcm(self.cache[path], area != "win")
        path = os.path.join(HERE, spec["nsf"])  # an NSF track
        if path not in self.nsf:
            self.nsf[path] = Music(path, self.rate)
        self.nsf[path].start(spec["track"])
        return self.nsf[path]

    def start(self, area):
        source = self._source(area)
        with self.lock:
            self.current = source

    def stop(self):
        with self.lock:
            self.current = None

    def mixer(self, sfx):
        if not self.on or self.paused or self.current is None:
            return sfx
        with self.lock:
            mus = self.current.render(len(sfx))
        return mix(sfx, mus, self.gain)


def audition(path, tracks, secs=10):
    import sounddevice as sd
    music = Music(path)
    for track in tracks:
        print(f"track {track} ...", flush=True)
        music.start(track)
        sd.play(music.render(RATE * secs), RATE, blocking=True)


if __name__ == "__main__":  # tools for picking tracks from an NSF of your own
    if sys.argv[1:2] == ["--survey"]:
        survey(sys.argv[2])
    elif sys.argv[1:2] == ["--audition"]:
        audition(sys.argv[2], [int(track) for track in sys.argv[3:]])
    elif sys.argv[1:2] == ["--play"]:
        play(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 20)
