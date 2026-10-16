"""The emulator: the Stella (Atari 2600) libretro core, loaded as a library and run one frame at a time.

Between frames the console is ours to read. The 2600 has no screen memory (the game draws each scanline as
the TV beam passes), so the whole machine state is just 128 bytes of RAM ($80-$FF) - the standard libretro
call retro_get_memory_data(SYSTEM_RAM) hands us a pointer to it, no core-specific symbols needed.

    core = Core(); core.load(rom_path)
    core.joy.add(JOY_UP); core.run()       # one frame with the joystick pushed up
    core.ram                               # the 128 bytes, live (indexed from $80)
    core.frame                             # the 2600's picture, 160x228 RGB
    AudioOut(rate).push(core.take_audio()) # play the game's sound

The core binary goes in cores/ (tools/get_core.sh). tools/ram_viewer.py is a raw viewer built on this.
"""

import ctypes as C
import os
import threading
import time

import numpy as np
import sounddevice as sd

from engine import paths

HERE, CORE, FROZEN, USER_DIR, SHOTS_DIR = paths.ROOT, paths.CORE, paths.FROZEN, paths.USER_DIR, paths.SCREENSHOTS
SYSTEM_DIR = os.fsencode(os.path.join(USER_DIR, "cores", "system"))
SAVE_DIR = os.fsencode(os.path.join(USER_DIR, "cores", "save"))
for _d in (SYSTEM_DIR, SAVE_DIR):
    os.makedirs(_d, exist_ok=True)

# libretro constants (libretro.h)
ENV_SET_ROTATION, ENV_GET_CAN_DUPE, ENV_GET_SYSTEM_DIRECTORY, ENV_SET_PIXEL_FORMAT = 1, 3, 9, 10
ENV_GET_VARIABLE, ENV_SET_VARIABLES, ENV_GET_VARIABLE_UPDATE = 15, 16, 17
ENV_GET_LOG_INTERFACE, ENV_GET_CORE_ASSETS_DIRECTORY, ENV_GET_SAVE_DIRECTORY = 27, 30, 31
OPTION_OVERRIDES = {}
PIXEL_0RGB1555, PIXEL_XRGB8888, PIXEL_RGB565 = 0, 1, 2
DEVICE_JOYPAD = 1
JOY_B, JOY_SELECT, JOY_START, JOY_UP, JOY_DOWN, JOY_LEFT, JOY_RIGHT = 0, 2, 3, 4, 5, 6, 7
MEMORY_SYSTEM_RAM = 2


class GameInfo(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]


class Geometry(C.Structure):
    _fields_ = [("base_width", C.c_uint), ("base_height", C.c_uint), ("max_width", C.c_uint),
                ("max_height", C.c_uint), ("aspect_ratio", C.c_float)]


class Timing(C.Structure):
    _fields_ = [("fps", C.c_double), ("sample_rate", C.c_double)]


class AVInfo(C.Structure):
    _fields_ = [("geometry", Geometry), ("timing", Timing)]


class Variable(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


ENV_CB = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_CB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO_CB = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIO_BATCH_CB = C.CFUNCTYPE(C.c_size_t, C.POINTER(C.c_int16), C.c_size_t)
POLL_CB = C.CFUNCTYPE(None)
STATE_CB = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
# retro_log_printf_t is variadic; on arm64 the named args (level, fmt) arrive in registers - log the format only
LOG_CB = C.CFUNCTYPE(None, C.c_int, C.c_char_p)
LOG_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")


class LogInterface(C.Structure):
    _fields_ = [("log", LOG_CB)]


@LOG_CB
def _core_log(level, fmt):
    if level >= 2 and fmt:
        print(f"[core {LOG_LEVELS[min(level, 3)]}] {fmt.decode(errors='replace').rstrip()}", flush=True)


class Core:
    def __init__(self, path=CORE):
        self.lib = C.CDLL(path)
        self.pixel_format = PIXEL_0RGB1555
        self.frame = None
        self.audio = []
        self.joy = set()  # joypad ids held (port 0 = left joystick + console switches)
        self.options = {}
        self._optbuf = {}
        self._keep = [ENV_CB(self._env), VIDEO_CB(self._video), AUDIO_CB(self._audio),
                      AUDIO_BATCH_CB(self._audio_batch), POLL_CB(lambda: None), STATE_CB(self._state)]
        L = self.lib
        L.retro_set_environment(self._keep[0])
        L.retro_set_video_refresh(self._keep[1])
        L.retro_set_audio_sample(self._keep[2])
        L.retro_set_audio_sample_batch(self._keep[3])
        L.retro_set_input_poll(self._keep[4])
        L.retro_set_input_state(self._keep[5])
        L.retro_get_memory_data.restype = C.c_void_p
        L.retro_get_memory_size.restype = C.c_size_t
        L.retro_init()
        self.ram = None  # numpy view of the 128 bytes, valid after load()

    # --- callbacks -------------------------------------------------------------------------
    def _env(self, cmd, data):
        cmd &= 0xFFFF  # strip the "experimental" flag
        if cmd == ENV_GET_CAN_DUPE:
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        if cmd in (ENV_GET_SYSTEM_DIRECTORY, ENV_GET_SAVE_DIRECTORY, ENV_GET_CORE_ASSETS_DIRECTORY):
            C.cast(data, C.POINTER(C.c_char_p))[0] = SAVE_DIR if cmd == ENV_GET_SAVE_DIRECTORY else SYSTEM_DIR
            return True
        if cmd == ENV_GET_LOG_INTERFACE:
            C.cast(data, C.POINTER(LogInterface))[0].log = _core_log
            return True
        if cmd == ENV_SET_PIXEL_FORMAT:
            self.pixel_format = C.cast(data, C.POINTER(C.c_int))[0]
            return self.pixel_format in (PIXEL_XRGB8888, PIXEL_RGB565)
        if cmd == ENV_SET_VARIABLES:  # "Description; default|other|..." -> default = first choice
            arr = C.cast(data, C.POINTER(Variable))
            i = 0
            while arr[i].key:
                desc = (arr[i].value or b"").decode(errors="replace")
                choices = desc.split("; ", 1)[1].split("|") if "; " in desc else [""]
                key = arr[i].key.decode()
                self.options[key] = OPTION_OVERRIDES.get(key, choices[0]).encode()
                i += 1
            return True
        if cmd == ENV_GET_VARIABLE:
            v = C.cast(data, C.POINTER(Variable))[0]
            key = v.key.decode() if v.key else ""
            if key not in self.options:
                return False
            self._optbuf[key] = C.c_char_p(self.options[key])  # keep the bytes alive for the core
            v.value = self._optbuf[key].value
            return True
        if cmd == ENV_GET_VARIABLE_UPDATE:
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        if cmd == ENV_SET_ROTATION:
            return True
        return False  # everything else: use the core's defaults

    def _video(self, data, w, h, pitch):
        if not data:
            return  # duped frame: keep the last one
        if self.pixel_format == PIXEL_XRGB8888:
            buf = np.ctypeslib.as_array(C.cast(data, C.POINTER(C.c_uint8)), shape=(h, pitch))
            px = buf[:, :w * 4].reshape(h, w, 4)
            self.frame = px[..., [2, 1, 0]].copy()
        else:  # RGB565
            buf = np.ctypeslib.as_array(C.cast(data, C.POINTER(C.c_uint16)), shape=(h, pitch // 2))[:, :w]
            r, g, b = (buf >> 11) & 31, (buf >> 5) & 63, buf & 31
            self.frame = np.dstack([r << 3, g << 2, b << 3]).astype(np.uint8)

    def _audio(self, l, r):
        self.audio.append(np.array([[l, r]], np.int16))

    def _audio_batch(self, data, frames):
        self.audio.append(np.ctypeslib.as_array(data, shape=(frames * 2,)).reshape(frames, 2).copy())
        return frames

    def _state(self, port, device, index, ident):
        if device == DEVICE_JOYPAD and port == 0:
            return 1 if ident in self.joy else 0
        return 0

    # --- API ------------------------------------------------------------------------------
    def av_info(self):
        info = AVInfo()
        self.lib.retro_get_system_av_info(C.byref(info))
        return info

    def load(self, path):
        game = GameInfo(path.encode(), None, 0, None)
        if not self.lib.retro_load_game(C.byref(game)):
            raise RuntimeError(f"core refused {path}")
        self.lib.retro_set_controller_port_device(0, DEVICE_JOYPAD)
        ptr = self.lib.retro_get_memory_data(MEMORY_SYSTEM_RAM)
        size = self.lib.retro_get_memory_size(MEMORY_SYSTEM_RAM)
        if not ptr or size < 128:
            raise RuntimeError(f"core exposes no system RAM (ptr={ptr}, size={size})")
        # a live view: reading it between retro_run() calls sees the current state, no copying, no pausing
        self.ram = np.ctypeslib.as_array(C.cast(ptr, C.POINTER(C.c_uint8)), shape=(128,))

    def run(self):
        self.lib.retro_run()

    def take_audio(self):
        a = np.concatenate(self.audio) if self.audio else np.zeros((0, 2), np.int16)
        self.audio = []
        return a


class AudioOut:
    """Ring buffer between the emulator (pushes each frame's samples) and the sound card (pulls at its pace).
    mixer(block) -> block, if given, runs INSIDE the sound card's callback on every block it asks for - so a
    source like the music (music.MusicPlayer) is rendered exactly when and as much as the card needs, and
    never stutters with the video loop's timing. Only the emulator's own samples go through the buffer.

    Fixed 512-frame blocks (~16 ms): with blocksize=0 the card asked for 15 frames at a time - ~2000 Python
    callbacks a second, which the game loop starved (clicks). The emulator side keeps a cushion: after it
    runs dry it isn't played again until `prime` samples are queued, so it never comes out in crumbs.
    The emulator makes 524 samples per frame; ~31423/s against the card's 31440/s at a 59.97 Hz loop."""

    def __init__(self, rate, max_ms=150, prime_ms=50, mixer=None, block=512):
        self.buf, self.lock = np.zeros((0, 2), np.int16), threading.Lock()
        self.max, self.prime = int(rate * max_ms / 1000), int(rate * prime_ms / 1000)
        self.mixer = mixer
        self.priming = True
        self.expect = True        # False while the game deliberately makes no sound (paused / room scroll)
        self.missing = 0          # emulator samples the card wanted but didn't get while expected (diagnostics)
        self.dropped = 0          # emulator samples thrown away because the buffer was full (diagnostics)
        self.xruns = 0            # the sound card's own "callback was late" flag = audible dropouts
        self.tap = None           # tap(block): sees every block exactly as played (recorder.py)
        self.stream = sd.OutputStream(samplerate=rate, channels=2, dtype="int16", callback=self._pull,
                                      blocksize=block, latency="high")
        self.stream.start()

    @property
    def underruns(self):  # old name, kept for callers
        return self.missing

    def _pull(self, out, frames, _time, status):
        if status.output_underflow:
            self.xruns += 1
        block = np.zeros((frames, 2), np.int16)
        with self.lock:
            if self.priming and len(self.buf) >= self.prime:
                self.priming = False
            if not self.priming:
                n = min(frames, len(self.buf))
                block[:n] = self.buf[:n]
                self.buf = self.buf[n:]
                if n < frames:
                    self.priming = True  # ran dry: refill the cushion before playing on
                    if self.expect:
                        self.missing += frames - n
        if self.mixer is not None:
            block = self.mixer(block)
        out[:] = block
        if self.tap is not None:
            self.tap(block)

    def push(self, samples):
        with self.lock:
            buf = np.concatenate([self.buf, samples])
            if len(buf) > self.max:  # never let latency grow
                self.dropped += len(buf) - self.max
                buf = buf[-self.max:]
            self.buf = buf
