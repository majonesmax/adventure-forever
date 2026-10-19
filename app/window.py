"""The game window: runs the emulator, asks the looks for pictures, and shows them.

One frame (GameWindow.run):
    1. input      keys -> the joystick, or window commands (KEYS below)
    2. the game   one emulator frame - unless paused, or a room scroll is sliding (the game waits for it)
    3. pictures   a GameState snapshot -> each look that's needed draws it (or the scroll's next frame)
    4. extras     music follows the area, the recorder saves every look, the RAM panel logs events
    5. show       the current view: a look beside the 2600 original, a look alone, the 2600 alone, or the
                  grid (what you're playing over a comparison left, the 2600 over its live RAM right)
    6. pace       vsync on a ~60 Hz display, else a timer at the game's frame rate

What's on screen is a look (the console: NES, SNES, VGA, paper) showing a cast (who) in a world (where), both
from packs/. L changes the look, C the cast, W the world, and a moment's overlay says what's showing
(now_showing.py; I brings it up without changing anything). The grid shows what you're playing (top) over a
comparison (bottom): by default the next look with the same cast and world. In the grid L / C / W change only
yours, and Shift+L / C / W only the comparison.
Until C or W is pressed each look shows its own pack's cast and world; after, every look shows the chosen
one, so the grid compares consoles.
"""

import collections
import os
import time
from typing import Any

import numpy as np
import pygame
from PIL import Image

import content
import looks
from app import debug_panel as DP
from app.fonts import mono
from app.help_panel import HelpPanel
from app.now_showing import NowShowing
from app import recorder as REC
from app import transitions as TR
from engine import ambience as AMB
from engine import effects as FX
from engine import emulator as h
from engine import music as MU
from engine import objects as O
from engine import paths
from engine import rooms as R
from engine import versions
from engine.footsteps import Footsteps
from engine.state import Game, GameState
from looks.base import RoomLook
from shared import layout as L
from shared.types import Picture, RamView, Samples

# the joystick: arrows + fire (space), and the console's two switches
JOYSTICK = {pygame.K_UP: h.JOY_UP, pygame.K_DOWN: h.JOY_DOWN, pygame.K_LEFT: h.JOY_LEFT,
            pygame.K_RIGHT: h.JOY_RIGHT, pygame.K_SPACE: h.JOY_B,
            pygame.K_TAB: h.JOY_SELECT, pygame.K_RETURN: h.JOY_START}
SHIFTED = {pygame.K_l: "compare_look", pygame.K_c: "compare_cast", pygame.K_w: "compare_world"}  # + Shift
KEYS = {  # window commands -> GameWindow method
    pygame.K_l: "next_look", pygame.K_c: "next_cast", pygame.K_w: "next_world", pygame.K_v: "next_view",
    pygame.K_t: "toggle_scrolls", pygame.K_p: "toggle_pause",
    pygame.K_m: "toggle_music", pygame.K_MINUS: "music_quieter", pygame.K_EQUALS: "music_louder",
    pygame.K_n: "next_music_source", pygame.K_s: "screenshot", pygame.K_r: "toggle_recording",
    pygame.K_d: "toggle_debug_line", pygame.K_i: "show_info", pygame.K_f: "toggle_fullscreen",
    pygame.K_h: "toggle_help"}  # every key, for players: app/controls.py (the help panel, H)

VIEWS = ("both", "look", "2600", "grid")
CAPTIONS = {"both": "Adventure Forever - remaster (left) and the 2600 original (right)",
            "look": "Adventure Forever - remaster", "2600": "Adventure Forever - the Atari 2600 original",
            "grid": "Adventure Forever - one game, four ways"}
CAPTIONS = {view: f"{text}  -  H for help" for view, text in CAPTIONS.items()}
SCALE = 3          # a 256x240 look -> 768x720
SIDE_SCALE = 2     # the 2600 picture beside it: 160x228 -> 2x wide (its pixels are wide) x 2 tall
SOLO_SCALE = 3     # the 2600 picture alone: 160x228 -> 960x684
QUAD = (512, 480)  # grid: each quadrant is a 256x240 screen at x2 -> a 1024x960 window
BACKGROUND = (16, 16, 24)
FIT = 0.9  # a new window takes at most this share of the screen's width and height
NOTHING_CARRIED = 0x12  # the game's "null" object
DEFAULT_SAMPLE_RATE = 31440
MadeKey = tuple[str, str | None, str | None]   # (look, cast, world): None = that look's own pack's
Tagged = tuple[Picture | None, str]            # a grid pane: its picture and its label


class GameWindow:
    def __init__(self, rom: str, look_key: str | None = None, cast_key: str | None = None,
                 world_key: str | None = None, grid: bool = False, public: bool = False,
                 record: bool = False):
        self.core = h.Core()
        self.core.load(rom)
        av_info = self.core.av_info()
        self.fps = av_info.timing.fps
        rate = int(av_info.timing.sample_rate) or DEFAULT_SAMPLE_RATE
        R.ROM_PATH = rom  # the looks read walls and graphics from the ROM too
        self.game = Game()
        self.public = public
        self.choose_starting_looks(look_key, cast_key, world_key)
        pygame.display.init()  # not pygame.init(): that opens pygame's own mixer too (a 2nd sound stream)
        pygame.font.init()
        self.start_sound(rate)
        self.panel = DP.DebugPanel(QUAD)
        self.recorder = REC.Recorder(paths.RECORDINGS, rate)
        self.audio.tap, self.panel.listener = self.recorder.audio_tap, self.recorder.event
        self.font = mono(14)
        self.tag_font = mono(12, bold=True)
        self.now_showing = NowShowing()
        self.help = HelpPanel()
        self.check_rom(rom)

        self.view = "grid" if grid else "both"
        self.debug = self.paused = False
        self.scrolling = True
        self.scrolls: dict[RoomLook, TR.Scroll] = {}  # look -> its room scroll while one is sliding
        self.state: GameState | None = None
        self.prev_state: GameState | None = None
        self.pictures: dict[RoomLook, Picture] = {}
        self.music_area: str | None = None
        self.frame_no = 0
        self.render_ms: list[float] = []
        self.frame_times: collections.deque[float] = collections.deque(maxlen=121)  # the real fps
        self.fullscreen = False
        self.vsync = False
        self.canvas = pygame.Surface((1, 1))   # set_mode() makes the real one
        self.screen = self.set_mode()
        self.choose_pacing()
        if record:
            self.toggle_recording()

    def choose_starting_looks(self, look_key: str | None, cast_key: str | None,
                              world_key: str | None) -> None:
        """What L, C and W cycle through, and what's on screen first. Default: the NES with its own pack in
        development; a packaged app starts on the SNES with its last private pack's cast and world, if it
        has one (packs bundled in a personal build only - not packs the player added: they wait for C / W)."""
        self.look_keys = list(looks.LOOKS)
        self.cast_keys, self.world_keys = content.casts(self.public), content.worlds(self.public)
        if look_key is not None:
            look_key = looks.OLD_NAMES.get(look_key, look_key)
        if look_key in looks.TEMPLATE_LOOKS:  # the template look is reachable by name only
            self.look_keys.append(look_key)
        for key, keys in ((cast_key, self.cast_keys), (world_key, self.world_keys)):
            if key and key not in keys:
                keys.append(key)
        bundled = []
        for key in self.cast_keys:
            folder = content.packs().get(key, "")
            if os.path.dirname(folder) == content.PRIVATE_PACKS:
                bundled.append(key)
        last_bundled = bundled[-1] if paths.FROZEN and bundled else None
        self.look_key: str = look_key or ("snes" if paths.FROZEN else "nes")
        self.cast_key: str | None = cast_key or last_bundled
        if world_key is None and last_bundled in self.world_keys:
            world_key = last_bundled
        self.world_key: str | None = world_key
        self.made: dict[MadeKey, RoomLook] = {}  # (look, cast, world) -> the look, made when first shown
        # the grid's comparison: its own look, cast and world where set; None = yours
        self.compare: dict[str, str | None] = {"look": None, "cast": None, "world": None}
        print(f"looks: {', '.join(self.look_keys)}; casts: {', '.join(self.cast_keys)}; worlds: "
              f"{', '.join(self.world_keys)} - starting in {self.look.key}", flush=True)

    def start_sound(self, rate: int) -> None:
        """The sound card, with the background music (engine/music.py) and the world's ambience
        (engine/ambience.py) mixed in its callback. The game runs without music if it can't start."""
        self.ambience = AMB.Ambience()
        self.footsteps = Footsteps(self.ambience)
        self.effects = FX.Effects()
        self.sound_ram: bytes | None = None     # last frame's RAM, to hear when the game starts a sound
        self.music: MU.MusicPlayer | None
        try:
            self.music = MU.MusicPlayer(rate=rate, public=self.public)
            self.music.use_world(self.look.world)
            print(f"music: {self.music.source_name}", flush=True)
        except Exception as err:
            print(f"no music: {err}", flush=True)
            self.music = None
        self.audio = h.AudioOut(rate, mixer=self.mix_sound)

    def mix_sound(self, block: Samples) -> Samples:
        """The sound card's callback: the 2600's sound or the look's effects, with the ambience under them,
        then the music."""
        block = MU.mix(block, self.ambience.render(len(block)))
        block = MU.mix(block, self.effects.render(len(block)))
        return self.music.mixer(block) if self.music else block

    @property
    def remastered_sound(self) -> bool:
        """The look's own sound effects - everywhere but the 2600-only view, which has the 2600's."""
        return self.view != "2600"

    def live_ram(self) -> RamView:
        """The core's live view of the game's 128 bytes of RAM."""
        assert self.core.ram is not None   # the ROM was loaded when the window was made
        return self.core.ram

    def game_sound(self) -> Samples:
        """This frame's sound from the game: the 2600's own, or - in a remastered view - silence, with the
        look's version of any sound the game just started."""
        samples = self.core.take_audio()
        ram = bytes(self.live_ram())
        started = FX.heard(self.sound_ram, ram) if self.sound_ram else []
        self.sound_ram = ram
        if not self.remastered_sound:
            return samples
        for name in started:
            self.effects.play(name, self.look.platform, self.look.cast.voices)
        return np.zeros_like(samples)

    def check_rom(self, rom: str) -> None:
        """A ROM that isn't the version this is made for: say so, and what it means (engine/versions.py)."""
        with open(rom, "rb") as f:
            self.rom_report = versions.report(f.read())
        self.now_showing.warning = self.rom_report
        if self.rom_report:
            headline, details = self.rom_report
            print("ROM: " + "\n     ".join([headline, *details]), flush=True)
        self.now_showing.show(duration=12 if self.rom_report else 2.5)  # say what's on screen at the start

    def choose_pacing(self) -> None:
        """Vsync paces the loop on a display near the game's rate; anything else, a timer (run())."""
        rates = []
        if hasattr(pygame.display, "get_desktop_refresh_rates"):
            rates = pygame.display.get_desktop_refresh_rates()
        self.display_hz_matches = bool(rates) and abs(rates[0] - self.fps) < 1.5
        pacing = "vsync" if self.vsync and self.display_hz_matches else "timer"
        print(f"display {rates[0] if rates else '?'} Hz, vsync {'on' if self.vsync else 'off'}, "
              f"pacing by {pacing}", flush=True)

    # ---- which looks ---------------------------------------------------------------------------------------

    def get(self, look_key: str, cast_key: str | None = None, world_key: str | None = None) -> RoomLook:
        """The look `look_key` with a cast and world (default: the chosen ones) - made once, then kept."""
        key = (look_key, cast_key or self.cast_key, world_key or self.world_key)
        if key not in self.made:
            self.made[key] = looks.make(*key, self.game.reader)
        return self.made[key]

    @property
    def look(self) -> RoomLook:
        """The look on screen."""
        return self.get(self.look_key)

    @property
    def comparison(self) -> RoomLook:
        """The grid's bottom pane: the comparison's own look, cast and world where set (Shift+L / C / W),
        else the look after yours, with your cast and world."""
        look_key = self.compare["look"] or following(self.look_keys, self.look_key)
        cast_key = self.compare["cast"] or self.look.cast.key
        world_key = self.compare["world"] or self.look.world.key
        return self.get(look_key, cast_key, world_key)

    def grid_looks(self) -> tuple[RoomLook, RoomLook]:
        """The grid's left column: what you're playing over the comparison."""
        return self.look, self.comparison

    def recorded_looks(self) -> list[RoomLook]:
        """While recording: every look in the L cycle (one stream each, named by the look), with the cast
        and world on screen."""
        return [self.get(look_key) for look_key in self.look_keys]

    # ---- the loop ------------------------------------------------------------------------------------------

    def run(self) -> None:
        clock = pygame.time.Clock()
        while self.handle_input():
            self.step_game()
            if self.core.frame is None:
                continue
            started = time.perf_counter()
            self.draw_pictures()
            self.record_frame()
            took_ms = (time.perf_counter() - started) * 1000
            self.render_ms = (self.render_ms + [took_ms])[-60:]  # the last second's
            self.show()
            # with vsync on a ~60 Hz display, flip() already paces us at the game's 60 fps; a second wait on
            # top would stack and stutter. Otherwise (no vsync, or e.g. a 120 Hz display) the clock paces us.
            clock.tick(0 if (self.vsync and self.display_hz_matches) else self.fps)

    def handle_input(self) -> bool:
        """Keys -> the joystick or a window command. False = quit."""
        for event in pygame.event.get():
            escape = event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
            if escape and self.help.open:
                self.help.toggle()  # Esc closes the help first; the next Esc quits
                continue
            if event.type == pygame.QUIT or escape:
                self.stop_recording()  # finish the files properly
                return False
            if event.type == pygame.DROPFILE:  # a pack (folder or .zip) dropped on the window
                self.install_pack(event.file)
            elif event.type in (pygame.KEYDOWN, pygame.KEYUP):
                self.handle_key(event)
        return True

    def handle_key(self, event: pygame.event.Event) -> None:
        pressed = event.type == pygame.KEYDOWN
        if event.key in JOYSTICK:
            if pressed:
                self.core.joy.add(JOYSTICK[event.key])
            else:
                self.core.joy.discard(JOYSTICK[event.key])
        elif pressed and event.key in SHIFTED and event.mod & pygame.KMOD_SHIFT:
            getattr(self, SHIFTED[event.key])()
        elif pressed and event.key in KEYS:
            getattr(self, KEYS[event.key])()

    def step_game(self) -> None:
        """One emulator frame - unless paused, or while a scroll slides (the game simply waits for it)."""
        waiting = self.paused or self.scrolls or self.help.open  # the game waits while the help is up too
        if not waiting:
            self.frame_times.append(time.perf_counter())
            self.core.run()
            self.audio.push(self.game_sound())  # the music is added in the sound card's callback
            self.frame_no += 1
            self.panel.update(None, self.live_ram(), self.frame_no)  # always, so the event log has history
        if self.music:
            self.music.paused = self.paused or self.help.open  # P and the help pause the music; scrolls don't
        self.audio.expect = not waiting  # silence is deliberate then

    def needed_looks(self) -> list[RoomLook]:
        """The looks that draw this frame: what's on screen - and while recording, every look's stream and
        the grid's comparison too (its own stream: it can have its own cast and world)."""
        needed = list(self.grid_looks()) if self.view == "grid" else [self.look]
        if self.recorder.active:
            recorded = self.recorded_looks()
            needed = recorded + [look for look in self.grid_looks() if look not in recorded]
        return needed

    def draw_pictures(self) -> None:
        """Every look that's needed draws this frame - or the next frame of its room scroll."""
        needed = self.needed_looks()
        if self.scrolls:
            self.continue_scrolls(needed)
            return
        state = self.state = self.game.state(self.live_ram())
        self.pictures = {look: look.draw(state, self.frame_no) for look in needed}
        before = self.prev_state
        into_next_room = before is not None and TR.scroll_direction(before, state)
        if self.scrolling and before is not None and into_next_room:
            for look in needed:
                scroll = TR.Scroll.between(look, before, state, self.frame_no)
                if scroll is not None:   # always, here: scroll_direction found a direction
                    self.scrolls[look] = scroll
            self.pictures = {look: scroll.frame() for look, scroll in self.scrolls.items()}
        just_won = state.won and not (self.prev_state and self.prev_state.won)
        if just_won:
            print(f"WIN detected (game {state.game}, frame {self.frame_no})", flush=True)
        self.prev_state = state
        self.follow_music(state)
        self.follow_ambience(state)

    def continue_scrolls(self, needed: list[RoomLook]) -> None:
        """The next frame of every look's room scroll. They all move the same distance at the same speed,
        so they finish together; a view switch mid-scroll (into the grid, say) can need a look that isn't
        scrolling yet - it joins at the same point."""
        caught_up = next(iter(self.scrolls.values())).offset
        for look in needed:
            if look in self.scrolls or self.prev_state is None or self.state is None:
                continue
            scroll = TR.Scroll.between(look, self.prev_state, self.state, self.frame_no)
            if scroll:
                scroll.offset = caught_up
                self.scrolls[look] = scroll
        self.pictures = {look: scroll.frame() for look, scroll in self.scrolls.items()}
        if all(scroll.done for scroll in self.scrolls.values()):
            self.scrolls = {}

    def follow_music(self, state: GameState) -> None:
        """Switch tracks when the music area changes (title / overworld / dungeon / final / win), and play
        them on the look's own band."""
        if self.music is None:
            return
        self.music.use_look(self.look.platform)
        area = MU.area_for(state)
        if area == self.music_area:
            return
        self.music_area = area
        if self.music.has(area):
            self.music.start(area)
        else:
            self.music.stop()

    def follow_ambience(self, state: GameState) -> None:
        """The world's sound for this room, heard while no music plays (M off, or a moment without a
        song) and the game isn't paused."""
        music_playing = self.music is not None and self.music.on and self.music.current is not None
        waiting = self.paused or self.help.open
        sound = self.look.world.sound(state.room_num)
        self.ambience.follow(sound, quiet=not music_playing and not waiting)
        if self.remastered_sound:
            self.footsteps.follow(state, sound, quiet=self.ambience.quiet)

    def record_frame(self) -> None:
        """One frame of every stream, and the log line (the RAM panel is rebuilt from RAM at edit time)."""
        state = self.state
        if not self.recorder.active or self.paused or state is None:
            return
        streams: dict[str, Picture | None] = {"a2600": self.core.frame,
                                              "compare": self.pictures.get(self.comparison)}
        for look in self.recorded_looks():
            streams[look.platform] = self.pictures.get(look)
        log_line: dict[str, Any] = {
            "g": self.frame_no, "room": state.room_num, "hero": state.hero, "carry": state.carried,
            "look": self.look.platform, "cast": self.look.cast.key, "world": self.look.world.key,
            "grid_top": self.look.platform, "grid16": self.comparison.platform,
            "compare": self.comparison.key, "view": self.view, "scroll": bool(self.scrolls)}
        self.recorder.frame(streams, log_line, self.live_ram())

    def show(self) -> None:
        main_w, main_h = L.SCREEN_W * SCALE, L.SCREEN_H * SCALE
        screen = self.canvas
        screen.fill(BACKGROUND)
        if self.view == "grid":
            top, bottom = self.grid_looks()
            playing = (self.pictures.get(top), f"PLAYING - {top.platform_name}")
            comparing = (self.pictures.get(bottom), f"COMPARE - {bottom.platform_name}")
            draw_grid(screen, self.core.frame, playing, comparing, self.panel, self.state, self.tag_font)
        if self.view in ("both", "look"):
            picture = self.pictures.get(self.look, next(iter(self.pictures.values())))
            surface = pygame.surfarray.make_surface(picture.transpose(1, 0, 2))
            screen.blit(pygame.transform.scale(surface, (main_w, main_h)), (0, 0))
        if self.view in ("both", "2600"):
            self.show_original(screen, main_w, main_h)
        self.show_overlays(screen, main_w)
        if self.debug:
            info = self.debug_line()
            screen.blit(self.font.render(info, True, (200, 200, 220)), (8, main_h + 4))
        if screen is not self.screen:  # a small screen, or a view changed in fullscreen: fit the canvas in
            fit_into(screen, self.screen)
        pygame.display.flip()

    def show_original(self, screen: pygame.Surface, main_w: int, main_h: int) -> None:
        """The 2600's own picture: beside the look (its pixels twice as wide as tall), or alone."""
        if self.core.frame is None:
            return
        original = pygame.surfarray.make_surface(self.core.frame.transpose(1, 0, 2))
        scale = SIDE_SCALE if self.view == "both" else SOLO_SCALE
        width, height = 160 * scale * 2, 228 * scale
        left = main_w + 16 if self.view == "both" else 0
        screen.blit(pygame.transform.scale(original, (width, height)), (left, (main_h - height) // 2))

    def show_overlays(self, screen: pygame.Surface, main_w: int) -> None:
        """What's showing (I), the help (H) and the recording light - window only, never in a recording."""
        centres = {"both": main_w // 2, "look": main_w // 2, "2600": 160 * SOLO_SCALE, "grid": QUAD[0]}
        changed_pane = (self.now_showing.changed or ("",))[0]
        panes: list[tuple[str | None, RoomLook]]
        if self.view == "grid" or changed_pane == "COMPARE":
            panes = [("PLAYING", self.look), ("COMPARE", self.comparison)]
        else:
            panes = [(None, self.look)]
        self.now_showing.draw(screen, panes, centres[self.view])
        self.help.draw(screen)
        blink_on = (self.frame_no // 30) % 2 == 0
        if self.recorder.active and blink_on:
            pygame.draw.circle(screen, (230, 40, 40), (18, 18), 7)
            screen.blit(self.font.render("REC", True, (230, 40, 40)), (30, 9))

    def debug_line(self) -> str:
        """D: the measured game speed, where the hero is, render time and sound diagnostics."""
        state, audio, times = self.state, self.audio, self.frame_times
        if state is None:
            return "no frame yet"
        carried = "-" if state.carried == NOTHING_CARRIED else O.NAMES.get(state.carried)
        fps = 0.0
        if len(times) > 1 and times[-1] > times[0]:
            fps = (len(times) - 1) / (times[-1] - times[0])
        hero_x, hero_y = state.hero
        return (f"game {fps:4.1f} fps   room ${state.room_num:02X} {state.room['name']}   "
                f"hero {hero_x:02X},{hero_y:02X}   carrying {carried}   "
                f"render {np.mean(self.render_ms):.1f} ms   "
                f"2600 audio missing {audio.missing} dropped {audio.dropped}  card dropouts {audio.xruns}")

    def set_mode(self) -> pygame.Surface:
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
        if self.fullscreen and pygame.display.get_surface() is not None:
            # fullscreen: the window is the whole screen whatever the view, so keep it - a new window would
            # leave fullscreen and come back (macOS animates that on every V); show() fits the canvas in
            pygame.display.set_caption(CAPTIONS[self.view])
            self.canvas = pygame.Surface(size)
            return self.screen
        if pygame.display.get_surface() is not None:  # pygame-ce 2.5.8 segfaults re-calling set_mode with
            pygame.display.quit()                      # SCALED|RESIZABLE (or vsync), so a new view gets a new
            pygame.display.init()                      # window - which never sees the release of a held key
            self.core.joy.clear()
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
        return surf

    # ---- window commands (KEYS) ----------------------------------------------------------------------------

    def keep_comparison(self, part: str) -> None:
        """Before L / C / W change what you play: in the grid, the comparison below stays exactly as it is
        (only Shift+L / C / W change it). Elsewhere it goes on following yours, so the grid opens on the look
        after yours with your cast and world."""
        if self.view == "grid":
            shown = self.comparison
            self.compare = {"look": shown.platform, "cast": shown.cast.key, "world": shown.world.key}
        else:
            self.compare[part] = None

    def next_look(self) -> None:
        """L: the next look (console), same cast and world - never changes the view."""
        self.keep_comparison("look")
        self.look_key = following(self.look_keys, self.look_key)
        self.now_showing.show(("PLAYING", "look"))
        print(f"look: {self.look.key}", flush=True)

    def next_cast(self) -> None:
        """C: the next cast, on every look."""
        self.keep_comparison("cast")
        self.cast_key = following(self.cast_keys, self.cast_key or self.look.cast.key)
        self.now_showing.show(("PLAYING", "cast"))
        print(f"cast: {self.look.cast.name} ({self.look.key})", flush=True)

    def next_world(self) -> None:
        """W: the next world, on every look."""
        self.keep_comparison("world")
        self.world_key = following(self.world_keys, self.world_key or self.look.world.key)
        self.now_showing.show(("PLAYING", "world"))
        if self.music:  # a world can bring its own soundtrack
            before = self.music.source_name
            self.music.use_world(self.look.world)
            if self.music.source_name != before:
                self.music_area = None
                print(f"music: {self.music.source_name}", flush=True)
        print(f"world: {self.look.world.name} ({self.look.key})", flush=True)

    def compare_look(self) -> None:
        """Shift+L: the grid comparison's next look."""
        self.compare["look"] = following(self.look_keys, self.comparison.platform)
        self.now_showing.show(("COMPARE", "look"))

    def compare_cast(self) -> None:
        """Shift+C: the grid comparison's next cast."""
        self.compare["cast"] = following(self.cast_keys, self.comparison.cast.key)
        self.now_showing.show(("COMPARE", "cast"))

    def compare_world(self) -> None:
        """Shift+W: the grid comparison's next world."""
        self.compare["world"] = following(self.world_keys, self.comparison.world.key)
        self.now_showing.show(("COMPARE", "world"))

    def toggle_fullscreen(self) -> None:
        """F: fullscreen on / off (the picture keeps its shape). Into fullscreen: the same window grows. Out
        of it: a new window at the current view's own size - whatever views were chosen meanwhile, and not
        the whole multiple of it that SCALED would otherwise pick (double, on a big screen)."""
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            pygame.display.toggle_fullscreen()
        else:
            self.screen = self.set_mode()

    def install_pack(self, path: str) -> None:
        """A folder or .zip dropped on the window: add the packs in it (content.install), show the first."""
        try:
            keys = content.install(path)
        except Exception as err:
            print(f"couldn't add {path}: {err}", flush=True)
            self.now_showing.show(note=f"COULDN'T ADD THAT: {err}"[:60], duration=5)
            return
        if not keys:
            self.now_showing.show(note="NO PACK IN THAT (A PACK HAS A PACK.JSON)", duration=5)
            return
        casts, worlds = content.casts(self.public), content.worlds(self.public)
        self.cast_keys = casts + [key for key in self.cast_keys if key not in casts]
        self.world_keys = worlds + [key for key in self.world_keys if key not in worlds]
        for made_key in list(self.made):  # looks made with an older copy of these packs: make them again
            _, cast_key, world_key = made_key
            if cast_key in keys or world_key in keys:
                del self.made[made_key]
        pack = content.load(keys[0])
        if pack.cast:
            self.cast_key, self.compare["cast"] = keys[0], None
        if pack.world:
            self.world_key, self.compare["world"] = keys[0], None
            if self.music:
                self.music.use_world(self.look.world)
                self.music_area = None
        names = ", ".join(content.load(key).name for key in keys)
        print(f"added: {names} -> {paths.USER_PACKS}", flush=True)
        self.now_showing.show(note=f"ADDED: {names}", duration=5)

    def toggle_help(self) -> None:
        """H: every key (app/controls.py); the game waits while it's open."""
        self.help.toggle()
        self.now_showing.shown_at = None  # one panel at a time

    def show_info(self) -> None:
        """I: the overlay naming the look, cast and world, without changing anything."""
        self.now_showing.show()

    def next_view(self) -> None:
        """V: side by side -> the look alone -> the 2600 alone -> the grid."""
        self.view = VIEWS[(VIEWS.index(self.view) + 1) % len(VIEWS)]
        self.screen = self.set_mode()

    def toggle_debug_line(self) -> None:
        self.debug = not self.debug
        self.screen = self.set_mode()

    def toggle_scrolls(self) -> None:
        self.scrolling = not self.scrolling

    def toggle_pause(self) -> None:
        self.paused = not self.paused

    def toggle_music(self) -> None:
        if self.music:
            self.music.on = not self.music.on

    def music_quieter(self) -> None:
        if self.music:
            self.music.gain = max(0.0, self.music.gain - 0.1)

    def music_louder(self) -> None:
        if self.music:
            self.music.gain = min(2.0, self.music.gain + 0.1)

    def next_music_source(self) -> None:
        if self.music:
            print(f"music: {self.music.next_source()}", flush=True)
            self.music_area = None  # restart this area's music from the new source

    def screenshot(self) -> None:
        """S: the look, the 2600 picture, the RAM (and the grid, in the grid view) to the screenshots
        folder."""
        frame_2600 = self.core.frame
        if frame_2600 is None or not self.pictures:
            return
        os.makedirs(paths.SCREENSHOTS, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        picture = self.pictures.get(self.look, next(iter(self.pictures.values())))
        Image.fromarray(picture).save(os.path.join(paths.SCREENSHOTS, f"{stamp}_{self.look.key}.png"))
        if self.view == "grid":
            pygame.image.save(self.canvas, os.path.join(paths.SCREENSHOTS, f"{stamp}_grid.png"))
        Image.fromarray(frame_2600).save(os.path.join(paths.SCREENSHOTS, f"{stamp}_2600.png"))
        np.save(os.path.join(paths.SCREENSHOTS, f"{stamp}_ram.npy"), self.live_ram().copy())
        print("saved", stamp, flush=True)

    def toggle_recording(self) -> None:
        """R: every look (with the cast and world on screen), the 2600 picture, the audio and a per-frame log
        (app/recorder.py)."""
        if self.recorder.active:
            self.stop_recording()
            return
        screen_size = (L.SCREEN_W, L.SCREEN_H)
        streams = {"a2600": (160, 228), "compare": screen_size}  # compare: the grid's lower pane
        for look_key in self.look_keys:
            streams[look_key] = screen_size
        game = self.state.game if self.state else 1
        where = self.recorder.start({"game": game}, streams)
        print(f"recording to {where}" if where else
              "can't record: ffmpeg isn't installed (https://ffmpeg.org/download.html)", flush=True)

    def stop_recording(self) -> None:
        if self.recorder.active:
            saved = self.recorder.stop()
            if saved is not None:
                print("recording saved:", *saved, "frames", flush=True)


def fit_into(canvas: pygame.Surface, screen: pygame.Surface) -> None:
    """Paint `canvas` into `screen` as big as fits with its shape kept, centred, bars around it."""
    canvas_w, canvas_h = canvas.get_size()
    screen_w, screen_h = screen.get_size()
    scale = min(screen_w / canvas_w, screen_h / canvas_h)
    w, h = int(canvas_w * scale), int(canvas_h * scale)
    if (w, h) == (screen_w, screen_h):
        pygame.transform.smoothscale(canvas, (screen_w, screen_h), screen)
        return
    screen.fill(BACKGROUND)
    screen.blit(pygame.transform.smoothscale(canvas, (w, h)), ((screen_w - w) // 2, (screen_h - h) // 2))


def following(keys: list[str], key: str | None) -> str:
    """The key after `key` in `keys`, round and round."""
    return keys[(keys.index(key) + 1) % len(keys)] if key in keys else keys[0]


def draw_grid(screen: pygame.Surface, frame_2600: Picture | None, top: Tagged, bottom: Tagged,
              panel: DP.DebugPanel, state: GameState | None, tag_font: pygame.font.Font) -> None:
    """The grid view: left column `top` over `bottom` ((picture, label) each: what you're playing and the
    comparison); right column the 2600 original over its RAM."""
    pane_w, pane_h = QUAD
    scale = min(pane_w / 320, pane_h / 228)  # the 2600's 160x228 has 2:1 wide pixels (= 320x228): fit it
    original_w, original_h = int(320 * scale), int(228 * scale)
    if frame_2600 is not None:
        original = pygame.surfarray.make_surface(frame_2600.transpose(1, 0, 2))
        centred = (pane_w + (pane_w - original_w) // 2, (pane_h - original_h) // 2)
        screen.blit(pygame.transform.scale(original, (original_w, original_h)), centred)
    for picture, (x, y) in ((top[0], (0, 0)), (bottom[0], (0, pane_h))):
        if picture is None:   # a pane with no picture yet (the first frames)
            continue
        surface = pygame.surfarray.make_surface(picture.transpose(1, 0, 2))
        screen.blit(pygame.transform.scale(surface, (pane_w, pane_h)), (x, y))
    if state is not None:
        ram_pane = pygame.Surface(QUAD)
        panel.draw(ram_pane, state)
        screen.blit(ram_pane, (pane_w, pane_h))
    labels = ((top[1], (0, 0)), ("ATARI 2600 - 1980", (pane_w, 0)),
              (bottom[1], (0, pane_h)), ("INTERNALS", (pane_w, pane_h)))
    for text, (x, y) in labels:  # each pane's name, bottom right on a dark box
        tag = tag_font.render(f" {text} ", True, (235, 235, 245))
        box = pygame.Surface((tag.get_width(), tag.get_height()), pygame.SRCALPHA)
        box.fill((0, 0, 0, 170))
        corner = (x + pane_w - tag.get_width() - 6, y + pane_h - tag.get_height() - 6)
        screen.blit(box, corner)
        screen.blit(tag, corner)
    pygame.draw.line(screen, (60, 60, 80), (pane_w, 0), (pane_w, 2 * pane_h), 2)
    pygame.draw.line(screen, (60, 60, 80), (0, pane_h), (2 * pane_w, pane_h), 2)
