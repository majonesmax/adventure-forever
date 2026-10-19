"""Gameplay recorder for play.py (R starts / stops): everything an editor needs, as separate clean streams.

recordings/<stamp>/ (frozen app: ~/Movies/Adventure Forever/<stamp>/)
  a2600.mp4   the 2600 picture, 160x228        } lossless H.264 RGB (libx264rgb -crf 0) at the native size -
  nes.mp4     the NES screen, 256x240          } scale up with nearest-neighbour when editing; one video
  snes.mp4    the SNES screen, 256x240         } frame per displayed frame (60 fps), including room scrolls,
  compare.mp4 the grid's comparison (its lower left pane) exactly as shown - with its own cast and world
  ram.bin     the 128 RAM bytes of every video frame (128 bytes each) - the internals panel is NOT drawn
              live (it cost the game its 60 fps); render_ram_video() rebuilds ram.mp4 from this at edit time
  audio.wav   exactly what the sound card played (2600 SFX + music), tapped from AudioOut's callback
  log.jsonl   one line per video frame: game frame, wall time, room, hero, carried, look, pack, view, + events
              (from debug_panel's event log: room changes, pickups, dragon states, deaths, wins, ...)
  meta.json   fps, sizes, sample rate, start time

Encoding and file writing happen on worker threads, so the game loop only copies arrays into queues.
"""

import json
import os
import queue
import shutil
import subprocess
import threading
import time
import wave
from typing import Any

import numpy as np

from shared.types import Picture, RamBytes, Samples

FPS = 60


def find_ffmpeg() -> str | None:
    """ffmpeg on the PATH - or, as apps started from the macOS Finder get a bare PATH, in Homebrew's places.
    None = not installed."""
    for path in (shutil.which("ffmpeg"), "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if path and os.path.exists(path):
            return path
    return None
FFMPEG: str | None = None
STREAMS = {"a2600": (160, 228), "nes": (256, 240)}  # + one per look in the L cycle (the window passes them)
RAM_SIZE = (512, 480)
Size = tuple[int, int]   # (width, height)


class _Video:
    """One ffmpeg process fed raw RGB frames from a queue on its own thread."""

    def __init__(self, path: str, size: Size, crf: int = 0):
        w, h = size
        self.size = size
        ffmpeg = FFMPEG or find_ffmpeg()
        if ffmpeg is None:
            raise RuntimeError("recording needs ffmpeg: https://ffmpeg.org/download.html")
        self.proc = subprocess.Popen(
            [ffmpeg, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
             "-r", str(FPS), "-i", "-", "-c:v", "libx264rgb", "-preset", "ultrafast", "-crf", str(crf), path],
            stdin=subprocess.PIPE)
        assert self.proc.stdin is not None   # opened as a pipe just above
        self.pipe = self.proc.stdin
        self.q: queue.Queue[Picture | None] = queue.Queue(maxsize=240)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while True:
            frame = self.q.get()
            if frame is None:
                break
            self.pipe.write(frame.tobytes())
        self.pipe.close()
        self.proc.wait()

    def put(self, frame: Picture) -> None:
        if frame.shape[1::-1] != self.size:  # (h, w, 3) must match; never let a bad frame kill the encoder
            frame = np.zeros((self.size[1], self.size[0], 3), np.uint8)
        self.q.put(np.ascontiguousarray(frame, np.uint8))

    def close(self) -> None:
        self.q.put(None)
        self.thread.join()


class Recorder:
    def __init__(self, root: str, rate: int):
        self.root, self.rate = root, rate
        self.active = False

    def start(self, info: dict[str, Any] | None = None, streams: dict[str, Size] | None = None) -> str | None:
        """-> the folder being written, or None when ffmpeg isn't available (nothing is started)."""
        global FFMPEG
        FFMPEG = find_ffmpeg()
        if FFMPEG is None:
            return None
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.dir = os.path.join(self.root, stamp)
        os.makedirs(self.dir, exist_ok=True)
        self.streams = dict(streams or STREAMS)
        self.videos = {name: _Video(os.path.join(self.dir, f"{name}.mp4"), size)
                       for name, size in self.streams.items()}
        self.ram_file = open(os.path.join(self.dir, "ram.bin"), "wb")
        self.wav = wave.open(os.path.join(self.dir, "audio.wav"), "wb")
        self.wav.setnchannels(2)
        self.wav.setsampwidth(2)
        self.wav.setframerate(self.rate)
        self.audio_q: queue.Queue[Samples | None] = queue.Queue()
        self.audio_thread = threading.Thread(target=self._audio_run, daemon=True)
        self.audio_thread.start()
        self.log = open(os.path.join(self.dir, "log.jsonl"), "w")
        self.frames, self.t0 = 0, time.perf_counter()
        self.pending: list[str] = []
        with open(os.path.join(self.dir, "meta.json"), "w") as f:
            meta = {"fps": FPS, "streams": self.streams, "audio_rate": self.rate, "started": stamp,
                    **(info or {})}
            json.dump(meta, f, indent=1)
        self.active = True
        return self.dir

    def _audio_run(self) -> None:
        while True:
            block = self.audio_q.get()
            if block is None:
                break
            self.wav.writeframes(block.tobytes())

    def audio_tap(self, block: Samples) -> None:
        """Called from the sound card's callback with each block it plays: just queue a copy."""
        if self.active:
            self.audio_q.put(block.copy())

    def event(self, text: str) -> None:
        if self.active:
            self.pending.append(text)

    def frame(self, images: dict[str, Picture | None], state: dict[str, Any], ram: RamBytes) -> None:
        """images: {stream name: HxWx3 uint8}; state: dict for the log line; ram: the 128 RAM bytes."""
        if not self.active:
            return
        self.ram_file.write(bytes(np.asarray(ram, np.uint8)))
        for name, video in self.videos.items():
            img = images.get(name)
            video.put(img if img is not None else np.zeros((video.size[1], video.size[0], 3), np.uint8))
        line = {"f": self.frames, "t": round(time.perf_counter() - self.t0, 4), **state}
        if self.pending:
            line["events"], self.pending = self.pending, []
        self.log.write(json.dumps(line) + "\n")
        self.frames += 1

    def stop(self) -> tuple[str, int] | None:
        if not self.active:
            return None
        self.active = False
        for video in self.videos.values():
            video.close()
        self.audio_q.put(None)
        self.audio_thread.join()
        self.wav.close()
        self.log.close()
        self.ram_file.close()
        # the videos are stamped 60 fps; if the loop ran at another rate, editing retimes them by this
        elapsed = time.perf_counter() - self.t0
        meta_path = os.path.join(self.dir, "meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        meta.update(frames=self.frames, seconds=round(elapsed, 3),
                    measured_fps=round(self.frames / elapsed, 3) if elapsed else None)
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=1)
        return self.dir, self.frames


def render_ram_video(folder: str) -> str:
    """Edit-time: rebuild the internals panel video (ram.mp4, 512x480, near-lossless) from ram.bin and
    log.jsonl, exactly as debug_panel would have drawn it live: the panel steps once per new game frame
    ('g')."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    from app import debug_panel as DP
    from engine.state import Game
    pygame.display.init()
    pygame.font.init()
    global FFMPEG
    FFMPEG = FFMPEG or find_ffmpeg()
    ram = np.fromfile(os.path.join(folder, "ram.bin"), np.uint8).reshape(-1, 128)
    with open(os.path.join(folder, "log.jsonl")) as f:
        games = [json.loads(line)["g"] for line in f]
    panel, surf, ren = DP.DebugPanel(RAM_SIZE), pygame.Surface(RAM_SIZE), Game()
    video = _Video(os.path.join(folder, "ram.mp4"), RAM_SIZE, crf=12)
    last_g = None
    for i in range(min(len(ram), len(games))):
        if games[i] != last_g:
            panel.update(None, ram[i], games[i])
            last_g = games[i]
        panel.draw(surf, ren.state(ram[i]))
        video.put(pygame.surfarray.array3d(surf).transpose(1, 0, 2))
    video.close()
    return os.path.join(folder, "ram.mp4")
