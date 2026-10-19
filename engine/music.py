"""Background music, one piece per AREA (title / overworld / dungeon / final / win), mixed under the 2600's
own sound effects in the sound card's callback.

Where each area's music comes from: the world on screen's own soundtrack if it has one (world/music.json -
content/world.py), then (first file found wins):
  private/music.json, music/music.json   {"title": {"nsf": "music/x.nsf", "track": 1},   an NSF via libgme
                                          "win": {"file": "music/win.wav"},              a WAV file
                                          "dungeon": {"song": "dungeon"}, ...}           a built-in song
  otherwise                               the built-in original songs (chiptune.py) - no files needed
The built-in songs are played by the look's own band (BANDS): the NES's chip, the SNES's orchestra, the VGA's
PC sound card, paper's toy box - switching looks keeps the place in the song. A world's own soundtrack keeps
the synth it names. Each song is made in the background the first time it's needed.
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
from typing import TYPE_CHECKING, Any, Callable

import numpy as np

from engine import paths
from engine.chiptune import Song
from shared.types import Samples

if TYPE_CHECKING:   # only for the type checker (importing them here would be circular)
    from content.world import World
    from engine.state import GameState

Spec = dict[str, Any]          # where an area's music comes from: a song, a WAV file or an NSF track
Config = dict[str, Spec]       # area -> its spec
Render = Callable[[Song], Samples]

HERE = paths.ROOT
NSF = None  # no NSF by default - see the music config above
GME_FILE = {"macos": "libgme.dylib", "windows": "gme.dll", "linux": "libgme.so"}[paths.SYSTEM]
LIB_PATHS = [os.path.join(HERE, "lib", GME_FILE),                     # bundled with a personal app build
             "/opt/homebrew/lib/libgme.dylib", "/usr/local/lib/libgme.dylib"]  # Homebrew (macOS)
RATE = 31440


def _lib() -> C.CDLL:
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

    def __init__(self, path: str, rate: int = RATE):
        self.lib = _lib()
        self.emu = C.c_void_p()
        err = self.lib.gme_open_file(path.encode(), C.byref(self.emu), rate)
        if err:
            raise RuntimeError(f"gme: {err.decode()}")
        self.lib.gme_ignore_silence(self.emu, 1)  # don't auto-end tracks on quiet passages
        self.tracks = self.lib.gme_track_count(self.emu)
        self.track: int | None = None

    def start(self, track: int) -> None:
        """track: 1-based like the NSF's own numbering."""
        err = self.lib.gme_start_track(self.emu, track - 1)
        if err:
            raise RuntimeError(f"gme: {err.decode()}")
        self.track = track

    def stop(self) -> None:
        self.track = None

    def render(self, frames: int) -> Samples:
        if self.track is None or frames <= 0:
            return np.zeros((max(frames, 0), 2), np.int16)
        buf = (C.c_short * (frames * 2))()
        self.lib.gme_play(self.emu, frames * 2, buf)
        return np.ctypeslib.as_array(buf).reshape(frames, 2).copy()

    def ended(self) -> bool:
        return bool(self.lib.gme_track_ended(self.emu))


def survey(path: str, seconds: int = 90) -> None:
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


def play(path: str, track: int, secs: int = 20) -> None:
    import sounddevice as sd
    music = Music(path)
    music.start(track)
    sd.play(music.render(RATE * secs), RATE, blocking=True)


CONFIGS = [os.path.join(HERE, "private", "music.json"), os.path.join(HERE, "music", "music.json")]
AREAS = ("title", "overworld", "dungeon", "final", "win")
FINAL_ROOMS = {0x13, 0x14, 0x15, 0x16, 0x1B}  # black maze + black castle interior: the "last dungeon"


BUILT_IN: Config = {area: {"song": area} for area in AREAS}


def load_configs() -> list[tuple[str, Config]]:
    """[(name, area -> source spec)]: every config file found, then the built-in songs (always there)."""
    import json
    found: list[tuple[str, Config]] = []
    for path in CONFIGS:
        if os.path.exists(path):
            with open(path) as f:
                config = {area: source for area, source in json.load(f).items() if not area.startswith("_")}
                found.append((os.path.relpath(path, HERE), config))
    return found + [("built-in songs", BUILT_IN)]


class Pcm:
    """A rendered piece (built-in song or WAV file) played from memory; loops unless it's a jingle."""

    def __init__(self, pcm: Samples, loop: bool):
        self.pcm, self.loop, self.pos = pcm, loop, 0

    def render(self, frames: int) -> Samples:
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


def read_wav(path: str, rate: int) -> Samples:
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


def area_for(state: "GameState") -> str:
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


def mix(sfx: Samples, mus: Samples, gain: float = 1.0) -> Samples:
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


def bands() -> dict[str, Render]:
    """Each look's band: look platform -> render(song dict) -> int16 stereo."""
    from engine import chiptune, orchestra, soundcard, toybox
    return {"nes": chiptune.render, "snes": orchestra.render, "vga": soundcard.render, "paper": toybox.render}


class MusicPlayer:
    """The music side of the mix, run from the sound card's callback (engine/emulator.py:
    AudioOut(mixer=...)).
    The game loop only says WHICH AREA to play (start/stop/on/gain/paused); the callback decides how much."""

    def __init__(self, rate: int = RATE, public: bool = False):
        import threading
        self.rate, self.lock = rate, threading.Lock()
        self.on, self.gain, self.paused = True, 1.0, False
        # the first source found plays; next_source() cycles. public: only the built-in songs
        self.base: list[tuple[str, Config]] = [("built-in songs", BUILT_IN)] if public else load_configs()
        self.configs = list(self.base)
        self.world: World | None = None
        self.which = 0
        self.current: Pcm | Music | None = None
        self.nsf: dict[str, Music] = {}
        self.cache: dict[Any, Samples] = {}       # a file's path, or (band or synth, song) -> its samples
        self.area: str | None = None              # the area asked for...
        self.playing_area: str | None = None      # ...and the one playing (they differ while one is made)
        self.look = "nes"
        self.bands = bands()
        self.making: set[Any] = set()

    @property
    def config(self) -> Config:
        return self.configs[self.which][1]

    @property
    def source_name(self) -> str:
        return self.configs[self.which][0]

    def next_source(self) -> str:
        self.which = (self.which + 1) % len(self.configs)
        return self.source_name

    def use_world(self, world: "World | None") -> None:
        """The world on screen: its soundtrack (if any) goes first and plays; N still cycles past it."""
        if world is self.world:
            return
        self.world = world
        own: list[tuple[str, Config]] = []
        if world is not None and world.music:
            synth, songs = world.music.get("synth", "chiptune"), world.music["songs"]
            own = [(f"{world.name} soundtrack", {area: {"world_song": songs[name], "synth": synth}
                                                 for area, name in world.music["areas"].items()})]
        self.configs, self.which = own + self.base, 0

    def has(self, area: str) -> bool:
        return area in self.config

    def use_look(self, look: str) -> None:
        """The look on screen (its platform: nes, snes...): its band plays the built-in songs from now on."""
        if look == self.look:
            return
        self.look = look
        if self.area is not None:
            self.start(self.area)

    def made_song(self, spec: Spec) -> tuple[Any, Callable[[], Samples]] | None:
        """(cache key, render) for a song this player makes itself, or None for a file or an NSF."""
        if "world_song" in spec:   # a world's own song, on the synth it names
            from engine import chiptune, fm
            synth = fm.render if spec["synth"] == "fm" else chiptune.render
            return (spec["synth"], id(spec["world_song"])), lambda: synth(spec["world_song"])
        if "song" in spec:
            from engine import chiptune
            band = self.bands.get(self.look, self.bands["nes"])
            return (self.look, spec["song"]), lambda: band(chiptune.SONGS[spec["song"]])
        return None

    def loops(self, spec: Spec, area: str) -> bool:
        if "world_song" in spec:
            return spec["world_song"].get("loop", True)
        if "song" in spec:
            from engine import chiptune
            return chiptune.SONGS[spec["song"]]["loop"]
        return area != "win"

    def _source(self, area: str) -> Pcm | Music:
        """A file or an NSF track, ready to play."""
        spec = self.config[area]
        if "file" in spec:
            path = os.path.join(HERE, spec["file"])
            if path not in self.cache:
                self.cache[path] = read_wav(path, self.rate)
            return Pcm(self.cache[path], area != "win")
        path = os.path.join(HERE, spec["nsf"])
        if path not in self.nsf:
            self.nsf[path] = Music(path, self.rate)
        self.nsf[path].start(spec["track"])
        return self.nsf[path]

    def start(self, area: str) -> None:
        """Play an area's music: now if it's made, else once it is (made in the background meanwhile)."""
        import threading
        self.area = area
        spec = self.config[area]
        made = self.made_song(spec)
        if made is None:
            self.play(area, self._source(area))
            return
        key, render = made
        if key in self.cache:
            self.play(area, Pcm(self.cache[key], self.loops(spec, area)))
            return
        if key in self.making:
            return
        self.making.add(key)

        def work() -> None:
            self.cache[key] = render()
            self.making.discard(key)
            still_wanted = self.made_song(self.config.get(area, {})) if self.area == area else None
            if still_wanted and still_wanted[0] == key:
                self.start(area)
        threading.Thread(target=work, daemon=True).start()

    def play(self, area: str, source: Pcm | Music) -> None:
        """Switch to a source; the same area on another band keeps its place in the song."""
        with self.lock:
            if isinstance(self.current, Pcm) and isinstance(source, Pcm) and area == self.playing_area:
                source.pos = self.current.pos % len(source.pcm)
            self.current, self.playing_area = source, area

    def stop(self) -> None:
        self.area = None
        with self.lock:
            self.current, self.playing_area = None, None

    def mixer(self, sfx: Samples) -> Samples:
        if not self.on or self.paused or self.current is None:
            return sfx
        with self.lock:
            mus = self.current.render(len(sfx))
        return mix(sfx, mus, self.gain)


def audition(path: str, tracks: list[int], secs: int = 10) -> None:
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
