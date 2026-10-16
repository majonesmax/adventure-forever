"""Gameplay recorder for play.py (R starts / stops): everything an editor needs, as separate clean streams.

recordings/<stamp>/ (frozen app: ~/Movies/Adventure Forever/<stamp>/)
  a2600.mp4   the 2600 picture, 160x228        } lossless H.264 RGB (libx264rgb -crf 0) at the native size -
  nes.mp4     the NES screen, 256x240          } scale up with nearest-neighbour when editing; one video
  snes.mp4    the SNES screen, 256x240         } frame per displayed frame (60 fps), including room scrolls,
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

import numpy as np

FPS = 60


def find_ffmpeg():
    """Apps started from Finder get a bare PATH, so look in Homebrew's places too. None = not installed."""
    for path in (shutil.which("ffmpeg"), "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if path and os.path.exists(path):
            return path
    return None
FFMPEG = None
STREAMS = {"a2600": (160, 228), "nes": (256, 240)}  # + one per look in the L cycle (the window passes them)
RAM_SIZE = (512, 480)


class _Video:
    """One ffmpeg process fed raw RGB frames from a queue on its own thread."""

    def __init__(self, path, size, crf=0):
        w, h = size
        self.size = size
        self.proc = subprocess.Popen(
            [FFMPEG, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
             "-r", str(FPS), "-i", "-", "-c:v", "libx264rgb", "-preset", "ultrafast", "-crf", str(crf), path],
            stdin=subprocess.PIPE)
        self.q = queue.Queue(maxsize=240)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while True:
            frame = self.q.get()
            if frame is None:
                break
            self.proc.stdin.write(frame.tobytes())
        self.proc.stdin.close()
        self.proc.wait()

    def put(self, frame):
        if frame.shape[1::-1] != self.size:  # (h, w, 3) must match; never let a bad frame kill the encoder
            frame = np.zeros((self.size[1], self.size[0], 3), np.uint8)
        self.q.put(np.ascontiguousarray(frame, np.uint8))

    def close(self):
        self.q.put(None)
        self.thread.join()


class Recorder:
    def __init__(self, root, rate):
        self.root, self.rate = root, rate
        self.active = False

    def start(self, info=None, streams=None):
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
        self.audio_q = queue.Queue()
        self.audio_thread = threading.Thread(target=self._audio_run, daemon=True)
        self.audio_thread.start()
        self.log = open(os.path.join(self.dir, "log.jsonl"), "w")
        self.frames, self.t0, self.pending = 0, time.perf_counter(), []
        with open(os.path.join(self.dir, "meta.json"), "w") as f:
            json.dump({"fps": FPS, "streams": self.streams, "audio_rate": self.rate, "started": stamp, **(info or {})},
                      f, indent=1)
        self.active = True
        return self.dir

    def _audio_run(self):
        while True:
            block = self.audio_q.get()
            if block is None:
                break
            self.wav.writeframes(block.tobytes())

    def audio_tap(self, block):
        """Called from the sound card's callback with each block it plays: just queue a copy."""
        if self.active:
            self.audio_q.put(block.copy())

    def event(self, text):
        if self.active:
            self.pending.append(text)

    def frame(self, images, state, ram):
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

    def stop(self):
        if not self.active:
            return None
        self.active = False
        for v in self.videos.values():
            v.close()
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


def render_ram_video(folder):
    """Edit-time: rebuild the internals panel video (ram.mp4, 512x480, near-lossless) from ram.bin + log.jsonl,
    exactly as debug_panel would have drawn it live: the panel steps once per new game frame ('g')."""
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
