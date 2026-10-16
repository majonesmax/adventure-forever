"""The game window: runs the emulator, asks the looks for pictures, and shows them.

One frame (GameWindow.run):
    1. input      keys -> the joystick, or window commands (KEYS below)
    2. the game   one emulator frame - unless paused, or a room scroll is sliding (the game waits for it)
    3. pictures   a GameState snapshot -> each look that's needed draws it (or the scroll's next frame)
    4. extras     music follows the area, the recorder saves every look, the RAM panel logs events
    5. show       the current view: a look beside the 2600 original, a look alone, the 2600 alone, or the
                  grid (the NES and SNES looks left, the 2600 over its live RAM right)

What's on screen is a look (the console: NES, SNES) showing a cast (who) in a world (where), both from packs/.
L changes the look, C the cast, W the world, and a moment's overlay says what's showing (now_showing.py; I
brings it up without changing anything).
Until C or W is pressed each look shows its own pack's cast and world; after, every look shows the chosen
one, so the grid compares consoles.
    6. pace       vsync on a ~60 Hz display, else a timer at the game's frame rate
"""

import collections
import os
import time

import numpy as np
import pygame
from PIL import Image

import content
import looks
from app import debug_panel as DP
from app.fonts import mono
from app.now_showing import NowShowing
from app import recorder as REC
from app import transitions as TR
from engine import emulator as h
from engine import music as MU
from engine import objects as O
from engine import paths
from engine import rooms as R
from engine import versions
from engine.state import Game
from shared import layout as L

# the joystick: arrows + fire (space), and the console's two switches
JOYSTICK = {pygame.K_UP: h.JOY_UP, pygame.K_DOWN: h.JOY_DOWN, pygame.K_LEFT: h.JOY_LEFT,
            pygame.K_RIGHT: h.JOY_RIGHT, pygame.K_SPACE: h.JOY_B,
            pygame.K_TAB: h.JOY_SELECT, pygame.K_RETURN: h.JOY_START}
KEYS = {  # window commands -> GameWindow method
    pygame.K_l: "next_look", pygame.K_c: "next_cast", pygame.K_w: "next_world", pygame.K_v: "next_view",
    pygame.K_t: "toggle_scrolls", pygame.K_p: "toggle_pause",
    pygame.K_m: "toggle_music", pygame.K_MINUS: "music_quieter", pygame.K_EQUALS: "music_louder",
    pygame.K_n: "next_music_source", pygame.K_s: "screenshot", pygame.K_r: "toggle_recording",
    pygame.K_d: "toggle_debug_line", pygame.K_i: "show_info", pygame.K_f: "toggle_fullscreen"}

VIEWS = ("both", "look", "2600", "grid")
CAPTIONS = {"both": "Adventure Forever - remaster (left) and the 2600 original (right)",
            "look": "Adventure Forever - remaster", "2600": "Adventure Forever - the Atari 2600 original",
            "grid": "Adventure Forever - one game, four ways"}
SCALE = 3          # a 256x240 look -> 768x720
SIDE_SCALE = 2     # the 2600 picture beside it: 160x228 -> 2x wide (its pixels are wide) x 2 tall
SOLO_SCALE = 3     # the 2600 picture alone: 160x228 -> 960x684
QUAD = (512, 480)  # grid: each quadrant is a 256x240 screen at x2 -> a 1024x960 window
BACKGROUND = (16, 16, 24)
FIT = 0.9  # a new window takes at most this share of the screen's width and height


class GameWindow:
    def __init__(self, rom, look_key=None, cast_key=None, world_key=None, grid=False, public=False, record=False):
        self.core = h.Core()
        self.core.load(rom)
        av = self.core.av_info()
        self.fps, rate = av.timing.fps, int(av.timing.sample_rate) or 31440
        R.ROM_PATH = rom  # the looks read walls and graphics from the ROM too
        self.game = Game()

        # L cycles the looks, C the casts, W the worlds (None: each look's own); a template is reachable by name
        self.public = public
        self.look_keys = list(looks.LOOKS)
        self.cast_keys, self.world_keys = content.casts(public), content.worlds(public)
        look_key = looks.OLD_NAMES.get(look_key, look_key)
        if look_key in looks.TEMPLATE_LOOKS:
            self.look_keys.append(look_key)
        for key, keys in ((cast_key, self.cast_keys), (world_key, self.world_keys)):
            if key and key not in keys:
                keys.append(key)
        # default: NES with its own pack in development; a packaged app starts on the SNES with its last private
        # pack's cast and world, if it has one
        private = [k for k in self.cast_keys if content.is_private(k)]
        last = private[-1] if paths.FROZEN and private else None
        self.look_key = look_key or ("snes" if paths.FROZEN else "nes")
        self.cast_key = cast_key or last
        self.world_key = world_key or (last if last in self.world_keys else None)
        self.made = {}  # (look, cast, world) -> the look, made the first time it's shown
        print(f"looks: {', '.join(self.look_keys)}; casts: {', '.join(self.cast_keys)}; worlds: "
              f"{', '.join(self.world_keys)} - starting in {self.look.key}", flush=True)

        pygame.display.init()  # not pygame.init(): that also opens pygame's own audio mixer, a 2nd stream on the card
        pygame.font.init()
        try:  # background music (engine/music.py), mixed in the sound card's callback; the game runs without it
            self.music = MU.MusicPlayer(rate=rate, public=public)
            print(f"music: {self.music.source_name}", flush=True)
        except Exception as err:
            print(f"no music: {err}", flush=True)
            self.music = None
        self.audio = h.AudioOut(rate, mixer=self.music.mixer if self.music else None)
        self.panel = DP.DebugPanel(QUAD)
        self.recorder = REC.Recorder(paths.RECORDINGS, rate)
        self.audio.tap, self.panel.listener = self.recorder.audio_tap, self.recorder.event
        self.font = mono(14)
        self.tag_font = mono(12, bold=True)
        self.now_showing = NowShowing()
        with open(rom, "rb") as f:  # a ROM that isn't the version this is made for: say so, and what it means
            self.now_showing.warning = self.rom_report = versions.report(f.read())
        if self.rom_report:
            print("ROM: " + "\n     ".join([self.rom_report[0], *self.rom_report[1]]), flush=True)
        self.now_showing.show(duration=12 if self.rom_report else 2.5)  # say what's on screen at the start

        self.view = "grid" if grid else "both"
        self.debug = self.paused = False
        self.scrolling, self.scrolls = True, {}  # scrolls: look -> its room scroll while one is sliding
        self.st = self.prev_st = None
        self.pictures = {}
        self.music_area = None
        self.frame_no, self.render_ms = 0, []
        self.frame_times = collections.deque(maxlen=121)  # when each of the last game frames ran: the real fps
        self.fullscreen = False
        self.vsync = False
        self.screen = self.set_mode()
        rates = pygame.display.get_desktop_refresh_rates() if hasattr(pygame.display, "get_desktop_refresh_rates") else []
        self.display_hz_matches = bool(rates) and abs(rates[0] - self.fps) < 1.5
        print(f"display {rates[0] if rates else '?'} Hz, vsync {'on' if self.vsync else 'off'}, "
              f"pacing by {'vsync' if self.vsync and self.display_hz_matches else 'timer'}", flush=True)
        if record:
            self.toggle_recording()

    # ---- which looks ---------------------------------------------------------------------------------------

    def get(self, look_key):
        """The look `look_key` with the chosen cast and world - made once, then kept."""
        key = (look_key, self.cast_key, self.world_key)
        if key not in self.made:
            self.made[key] = looks.make(*key, self.game.reader)
        return self.made[key]

    @property
    def look(self):
        """The look on screen."""
        return self.get(self.look_key)

    def grid_looks(self):
        """The grid's left column: the NES look over the SNES look, with the same cast and world."""
        return self.get("nes"), self.get("snes")

    def recorded_looks(self):
        """While recording: every look in the L cycle (one stream each, named by the look), with the cast
        and world on screen."""
        return [self.get(k) for k in self.look_keys]

    # ---- the loop ------------------------------------------------------------------------------------------

    def run(self):
        clock = pygame.time.Clock()
        while self.handle_input():
            self.step_game()
            if self.core.frame is None:
                continue
            t0 = time.perf_counter()
            self.draw_pictures()
            self.record_frame()
            self.render_ms = (self.render_ms + [(time.perf_counter() - t0) * 1000])[-60:]
            self.show()
            # with vsync on a ~60 Hz display, flip() already paces us at the game's 60 fps; a second wait on
            # top would stack and stutter. Otherwise (no vsync, or e.g. a 120 Hz display) the clock paces us.
            clock.tick(0 if (self.vsync and self.display_hz_matches) else self.fps)

    def handle_input(self):
        """Keys -> the joystick or a window command. False = quit."""
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                self.stop_recording()  # finish the files properly
                return False
            if e.type in (pygame.KEYDOWN, pygame.KEYUP):
                if e.key in JOYSTICK:
                    (self.core.joy.add if e.type == pygame.KEYDOWN else self.core.joy.discard)(JOYSTICK[e.key])
                elif e.type == pygame.KEYDOWN and e.key in KEYS:
                    getattr(self, KEYS[e.key])()
        return True

    def step_game(self):
        """One emulator frame - unless paused, or while a scroll slides (the game simply waits for it)."""
        if not self.paused and not self.scrolls:
            self.frame_times.append(time.perf_counter())
            self.core.run()
            self.audio.push(self.core.take_audio())  # the music is added by the sound card's callback, not here
            self.frame_no += 1
            self.panel.update(None, self.core.ram, self.frame_no)  # always, so the event log has history
        if self.music:
            self.music.paused = self.paused  # P pauses the music too; scrolls don't
        self.audio.expect = not self.paused and not self.scrolls  # silence from the game is deliberate then

    def draw_pictures(self):
        """Every look that's needed draws this frame (all of them while recording)."""
        needed = (self.recorded_looks() if self.recorder.active else list(self.grid_looks()) if self.view == "grid"
                  else [self.look])
        if self.scrolls:  # every look scrolls the same distance at the same speed, so they finish together
            self.pictures = {lk: sc.frame() for lk, sc in self.scrolls.items()}
            if all(sc.done for sc in self.scrolls.values()):
                self.scrolls = {}
            return
        st = self.st = self.game.state(self.core.ram)
        self.pictures = {lk: lk.draw(st, self.frame_no) for lk in needed}
        if self.scrolling and self.prev_st and TR.scroll_direction(self.prev_st, st):  # into the next room
            self.scrolls = {lk: TR.Scroll.between(lk, self.prev_st, st, self.frame_no) for lk in needed}
            self.pictures = {lk: sc.frame() for lk, sc in self.scrolls.items()}
        if st.won and not (self.prev_st and self.prev_st.won):
            print(f"WIN detected (game {st.game}, frame {self.frame_no})", flush=True)
        self.prev_st = st
        if self.music is not None:  # switch tracks when the music area changes (title / overworld / ...)
            area = MU.area_for(st)
            if area != self.music_area:
                self.music_area = area
                self.music.start(area) if self.music.has(area) else self.music.stop()

    def record_frame(self):
        if self.recorder.active and not self.paused:  # the RAM panel is rebuilt from the RAM at edit time
            st = self.st
            self.recorder.frame({"a2600": self.core.frame,
                                 **{lk.platform: self.pictures.get(lk) for lk in self.recorded_looks()}},
                                {"g": self.frame_no, "room": st.room_num, "hero": st.hero, "carry": st.carried,
                                 "look": self.look.platform, "cast": self.look.cast.key,
                                 "world": self.look.world.key, "grid16": "snes",
                                 "view": self.view, "scroll": bool(self.scrolls)}, self.core.ram)

    def show(self):
        main_w, main_h = L.SCREEN_W * SCALE, L.SCREEN_H * SCALE
        screen = self.canvas
        screen.fill(BACKGROUND)
        if self.view == "grid":
            top, bottom = self.grid_looks()
            draw_grid(screen, self.core.frame, (self.pictures.get(top), top.platform_name),
                      (self.pictures.get(bottom), bottom.platform_name), self.panel, self.st, self.tag_font)
        if self.view in ("both", "look"):
            picture = self.pictures.get(self.look, next(iter(self.pictures.values())))
            surf = pygame.surfarray.make_surface(picture.transpose(1, 0, 2))
            screen.blit(pygame.transform.scale(surf, (main_w, main_h)), (0, 0))
        if self.view in ("both", "2600"):
            original = pygame.surfarray.make_surface(self.core.frame.transpose(1, 0, 2))
            if self.view == "both":
                side_w, side_h = 160 * SIDE_SCALE * 2, 228 * SIDE_SCALE
                screen.blit(pygame.transform.scale(original, (side_w, side_h)), (main_w + 16, (main_h - side_h) // 2))
            else:
                solo_w, solo_h = 160 * SOLO_SCALE * 2, 228 * SOLO_SCALE
                screen.blit(pygame.transform.scale(original, (solo_w, solo_h)), (0, (main_h - solo_h) // 2))
        centre = {"both": main_w // 2, "look": main_w // 2, "2600": 160 * SOLO_SCALE, "grid": QUAD[0]}[self.view]
        self.now_showing.draw(screen, self.look, centre)  # window only - never in the recording
        if self.recorder.active and (self.frame_no // 30) % 2 == 0:  # window only - never in the recording
            pygame.draw.circle(screen, (230, 40, 40), (18, 18), 7)
            screen.blit(self.font.render("REC", True, (230, 40, 40)), (30, 9))
        if self.debug:
            st, a = self.st, self.audio
            carried = O.NAMES.get(st.carried) if st.carried != 0x12 else "-"
            t = self.frame_times
            fps = (len(t) - 1) / (t[-1] - t[0]) if len(t) > 1 and t[-1] > t[0] else 0.0
            info = (f"game {fps:4.1f} fps   room ${st.room_num:02X} {st.room['name']}   "
                    f"hero {st.hero[0]:02X},{st.hero[1]:02X}   carrying {carried}   "
                    f"render {np.mean(self.render_ms):.1f} ms   "
                    f"2600 audio missing {a.missing} dropped {a.dropped}  card dropouts {a.xruns}")
            screen.blit(self.font.render(info, True, (200, 200, 220)), (8, main_h + 4))
        if screen is not self.screen:  # a small screen: the canvas shrunk into the window
            pygame.transform.smoothscale(screen, self.screen.get_size(), self.screen)
        pygame.display.flip()

    def set_mode(self):
        """The window for the current view. Each view is drawn at a fixed size (self.canvas) and shown scaled
        to the window (SCALED): it can be resized or made fullscreen (F), the picture keeping its shape with
        bars around it. On a screen too small for the view, the window opens at a size that fits (FIT) and
        the canvas is shrunk into it each frame. Vsync where the system offers it (flip waits for the
        display's refresh - no tearing, which room scrolls made obvious)."""
        main_w, main_h = L.SCREEN_W * SCALE, L.SCREEN_H * SCALE
        width = {"both": main_w + 16 + 160 * SIDE_SCALE * 2, "look": main_w, "2600": 160 * SOLO_SCALE * 2,
                 "grid": 2 * QUAD[0]}[self.view]
        height = 2 * QUAD[1] if self.view == "grid" else main_h
        size = (width, height + (24 if self.debug else 0))
        screen_w, screen_h = pygame.display.get_desktop_sizes()[0]
        k = min(1.0, FIT * screen_w / size[0], FIT * screen_h / size[1])
        shown = (int(size[0] * k), int(size[1] * k))
        pygame.display.set_caption(CAPTIONS[self.view])
        flags = pygame.SCALED | pygame.RESIZABLE
        try:
            surf = pygame.display.set_mode(shown, flags, vsync=1)
            self.vsync = True
        except pygame.error as err:
            print(f"vsync unavailable ({err}); expect some tearing", flush=True)
            surf = pygame.display.set_mode(shown, flags)
            self.vsync = False
        self.canvas = surf if k == 1.0 else pygame.Surface(size)
        if self.fullscreen:
            pygame.display.toggle_fullscreen()
        return surf

    # ---- window commands (KEYS) ----------------------------------------------------------------------------

    def next_look(self):
        """L: the next look (console), same cast and world - never changes the view."""
        self.look_key = self.look_keys[(self.look_keys.index(self.look_key) + 1) % len(self.look_keys)]
        self.now_showing.show("look")
        print(f"look: {self.look.key}", flush=True)

    def next_cast(self):
        """C: the next cast, on every look."""
        self.cast_key = following(self.cast_keys, self.cast_key or self.look.cast.key)
        self.now_showing.show("cast")
        print(f"cast: {self.look.cast.name} ({self.look.key})", flush=True)

    def next_world(self):
        """W: the next world, on every look."""
        self.world_key = following(self.world_keys, self.world_key or self.look.world.key)
        self.now_showing.show("world")
        print(f"world: {self.look.world.name} ({self.look.key})", flush=True)

    def toggle_fullscreen(self):
        """F: fullscreen on / off (the picture keeps its shape)."""
        self.fullscreen = not self.fullscreen
        pygame.display.toggle_fullscreen()

    def show_info(self):
        """I: the overlay naming the look, cast and world, without changing anything."""
        self.now_showing.show()

    def next_view(self):
        """V: side by side -> the look alone -> the 2600 alone -> the grid."""
        self.view = VIEWS[(VIEWS.index(self.view) + 1) % len(VIEWS)]
        self.screen = self.set_mode()

    def toggle_debug_line(self):
        self.debug = not self.debug
        self.screen = self.set_mode()

    def toggle_scrolls(self):
        self.scrolling = not self.scrolling

    def toggle_pause(self):
        self.paused = not self.paused

    def toggle_music(self):
        if self.music:
            self.music.on = not self.music.on

    def music_quieter(self):
        if self.music:
            self.music.gain = max(0.0, self.music.gain - 0.1)

    def music_louder(self):
        if self.music:
            self.music.gain = min(2.0, self.music.gain + 0.1)

    def next_music_source(self):
        if self.music:
            print(f"music: {self.music.next_source()}", flush=True)
            self.music_area = None  # restart this area's music from the new source

    def screenshot(self):
        """S: the look, the 2600 picture, the RAM (and the grid, in the grid view) to the screenshots folder."""
        if self.core.frame is None or not self.pictures:
            return
        os.makedirs(paths.SCREENSHOTS, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        picture = self.pictures.get(self.look, next(iter(self.pictures.values())))
        Image.fromarray(picture).save(os.path.join(paths.SCREENSHOTS, f"{stamp}_{self.look.key}.png"))
        if self.view == "grid":
            pygame.image.save(self.canvas, os.path.join(paths.SCREENSHOTS, f"{stamp}_grid.png"))
        Image.fromarray(self.core.frame).save(os.path.join(paths.SCREENSHOTS, f"{stamp}_2600.png"))
        np.save(os.path.join(paths.SCREENSHOTS, f"{stamp}_ram.npy"), self.core.ram.copy())
        print("saved", stamp, flush=True)

    def toggle_recording(self):
        """R: every look (with the cast and world on screen), the 2600 picture, the audio and a per-frame log
        (app/recorder.py)."""
        if self.recorder.active:
            self.stop_recording()
            return
        streams = {"a2600": (160, 228), **{k: (L.SCREEN_W, L.SCREEN_H) for k in self.look_keys}}
        game = self.st.game if self.st else 1
        where = self.recorder.start({"game": game}, streams)
        print(f"recording to {where}" if where else
              "can't record: ffmpeg isn't installed (https://ffmpeg.org/download.html)", flush=True)

    def stop_recording(self):
        if self.recorder.active:
            print("recording saved:", *self.recorder.stop(), "frames", flush=True)


def following(keys, key):
    """The key after `key` in `keys`, round and round."""
    return keys[(keys.index(key) + 1) % len(keys)] if key in keys else keys[0]


def draw_grid(screen, frame_2600, top, bottom, panel, st, tag_font):
    """The grid view: left column `top` over `bottom` ((picture, label) each: the NES and SNES looks); right
    column the 2600 original over its RAM."""
    qw, qh = QUAD
    k = min(qw / 320, qh / 228)  # the 2600's 160x228 has 2:1 wide pixels (= 320x228): fit it, centred
    w26, h26 = int(320 * k), int(228 * k)
    original = pygame.surfarray.make_surface(frame_2600.transpose(1, 0, 2))
    screen.blit(pygame.transform.scale(original, (w26, h26)), (qw + (qw - w26) // 2, (qh - h26) // 2))
    for img, (x, y) in ((top[0], (0, 0)), (bottom[0], (0, qh))):
        surf = pygame.surfarray.make_surface(img.transpose(1, 0, 2))
        screen.blit(pygame.transform.scale(surf, (qw, qh)), (x, y))
    pane = pygame.Surface(QUAD)
    panel.draw(pane, st)
    screen.blit(pane, (qw, qh))
    for text, (x, y) in ((top[1], (0, 0)), ("ATARI 2600 - 1980", (qw, 0)),
                         (bottom[1], (0, qh)), ("INTERNALS", (qw, qh))):
        tag = tag_font.render(f" {text} ", True, (235, 235, 245))
        box = pygame.Surface((tag.get_width(), tag.get_height()), pygame.SRCALPHA)
        box.fill((0, 0, 0, 170))
        pos = (x + qw - tag.get_width() - 6, y + qh - tag.get_height() - 6)
        screen.blit(box, pos)
        screen.blit(tag, pos)
    pygame.draw.line(screen, (60, 60, 80), (qw, 0), (qw, 2 * qh), 2)
    pygame.draw.line(screen, (60, 60, 80), (0, qh), (2 * qw, qh), 2)
