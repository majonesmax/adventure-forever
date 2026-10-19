"""Make a sizzle reel without anyone playing: the real app runs offscreen, a script presses its keys frame by
frame, and every frame the window draws becomes a frame of the video, with captions under it.

What's on screen is exactly what a player sees (the looks, the views, the info pop-up, the help panel, room
scrolls), and the sound is exactly what they'd hear: the 2600's own sound from the emulator plus the music,
mixed frame by frame, so it can't drift. The clock is virtual - a frame is 1/60 s of video however long it
takes to draw - so the reel is the same every time it's made.

Scenes are set up by writing the game's RAM between shots (the hero placed in a room, an item in his hand),
like loading a save; from there the real game plays it out. During play the app never writes RAM.

Usage: ADVENTURE_PACKS=../shall-we-play-a-game/packs python tools/make_reel.py [-o shots/reel.mp4]
       python tools/make_reel.py --stills 30    every 30th frame as a PNG in shots/reel_stills/, no video
Needs ffmpeg, your ROM and the emulator core. Writes the video, and its captions as an .srt beside it.
"""

import argparse
import os
import subprocess
import sys
import wave
from typing import Any, Callable, Iterable

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # no window
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, as a script

import numpy as np  # noqa: E402
import pygame  # noqa: E402
from PIL import Image  # noqa: E402

import content  # noqa: E402
from app import now_showing as NS  # noqa: E402
from app import recorder as REC  # noqa: E402
from app import window as WIN  # noqa: E402
from app.fonts import mono  # noqa: E402
from engine import emulator as h  # noqa: E402
from engine import paths  # noqa: E402
from shared.types import Picture, RamView, Rgb, Samples  # noqa: E402

CardLine = tuple[str, int, Rgb]     # a title card's line: (text, size, colour)
Caption = tuple[int, int, str]      # (first frame, last frame, text)

WIDTH, HEIGHT, FPS = 1920, 1080, 60
STAGE_H = 960                       # the app's picture goes in the top 1920x960; captions below
BACKGROUND = (11, 11, 20)
INK, DIM = (236, 236, 244), (150, 150, 170)
READ_FRAMES = int(2.6 * 60)         # every caption stays up at least this long...
READ_SPEED = 18                     # ...and longer ones at this many characters a second


class Clock:
    """The video's clock: the info pop-up and the help panel ask it the time instead of the wall."""
    now = 0.0

    @classmethod
    def perf_counter(cls) -> float:
        return cls.now


class CapturedAudio:
    """Stands in for the sound card (engine/emulator.AudioOut): keeps the emulator's samples for the frame
    being made. The reel mixes them with the music itself, a frame's worth at a time."""

    def __init__(self, rate: int, mixer: Callable[[Samples], Samples] | None = None, **_: Any):
        self.rate, self.mixer = rate, mixer
        self.pending: list[Samples] = []
        self.tap, self.expect, self.missing, self.dropped, self.xruns = None, True, 0, 0, 0

    def push(self, samples: Samples) -> None:
        self.pending.append(samples)

    def take(self, count: int) -> Samples:
        """Exactly `count` samples for this frame: the emulator's (silence while paused or scrolling) + the
        music."""
        sfx = np.concatenate(self.pending) if self.pending else np.zeros((0, 2), np.int16)
        self.pending = []
        block = np.zeros((count, 2), np.int16)
        block[:min(count, len(sfx))] = sfx[:count]
        return self.mixer(block) if self.mixer else block


def ffmpeg() -> str:
    found = REC.find_ffmpeg()
    if found is None:
        raise SystemExit("the reel needs ffmpeg: https://ffmpeg.org/download.html")
    return found


def never_records(recorder: REC.Recorder, *_args: Any, **_kwargs: Any) -> None:
    """In place of the recorder's __init__: a recorder that's never active."""
    recorder.active = False


class Reel:
    def __init__(self, rom: str, out: str, stills: int = 0):
        NS.time = Clock                                  # the pop-ups fade on the video's clock
        h.AudioOut = CapturedAudio                       # no sound card: the reel mixes the sound itself
        setattr(REC.Recorder, "__init__", never_records)  # replacing a method, deliberately
        WIN.SCALE, WIN.SOLO_SCALE = 4, 4                 # every view fits 1920x960 at its native size
        self.win = WIN.GameWindow(rom, look_key="nes", public=True)
        # the public packs, then the demos from ADVENTURE_PACKS - never private ones
        extra = [k for k in content.packs() if os.path.dirname(content.packs()[k]) in content.EXTRA_PACKS]
        self.win.cast_keys += [k for k in extra if content.load(k).cast]
        self.win.world_keys += [k for k in extra if content.load(k).world]
        self.out, self.stills, self.frame = out, stills, 0
        self.rate = self.sound.rate
        self.samples_done = 0
        self.captions: list[Caption] = []
        self.caption: str | None = None
        self.caption_from = 0
        self.font, self.small = mono(40, bold=True), mono(26)
        self.audio: list[Samples] = []
        self.video: subprocess.Popen[bytes] | None = None
        if not stills:
            self.video = subprocess.Popen(
                [ffmpeg(), "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                 "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                 "-crf", "16", "-pix_fmt", "yuv420p", out + ".video.mp4"], stdin=subprocess.PIPE)
        else:
            os.makedirs(out, exist_ok=True)

    @property
    def sound(self) -> CapturedAudio:
        audio = self.win.audio
        assert isinstance(audio, CapturedAudio)   # put in place of the sound card before the window was made
        return audio

    @property
    def ram(self) -> RamView:
        ram = self.win.core.ram
        assert ram is not None   # the window loaded the ROM
        return ram

    # ---- the script's verbs -----------------------------------------------------------------------------

    def say(self, text: str | None = None) -> None:
        """The caption from now on (None: none). The one before stays up long enough to read: the game
        carries on, nothing pressed, until it has."""
        if self.caption:
            need = max(READ_FRAMES, int(len(self.caption) / READ_SPEED * FPS))
            if self.frame - self.caption_from < need:
                self.play(need - (self.frame - self.caption_from))
        if self.caption:
            self.captions.append((self.caption_from, self.frame, self.caption))
        self.caption, self.caption_from = text, self.frame

    def play(self, frames: int, keys: Iterable[int] = ()) -> None:
        """Run the game for `frames` frames with these joystick directions held (h.JOY_*)."""
        for _ in range(frames):
            self.win.core.joy.clear()
            self.win.core.joy.update(keys)
            self.step()

    def press(self, command: str, then: int = 0) -> None:
        """A window command, as its key would (a GameWindow method name: "next_look", "next_view"...)."""
        getattr(self.win, command)()
        self.play(then)

    def walk_to(self, x: int, y: int, most: int = 600, near: int = 2) -> int:
        """Walk the hero toward (x, y) in the game's units (y counts up) - stops there, or after `most`
        frames (a wall in the way). Returns the frames it took."""
        hero_x = hero_y = 0
        for i in range(most):
            hero_x, hero_y = int(self.ram[0x8B - 0x80]), int(self.ram[0x8C - 0x80])
            if abs(hero_x - x) <= near and abs(hero_y - y) <= near:
                return i
            keys: set[int] = set()
            if abs(hero_x - x) > near:
                keys.add(h.JOY_RIGHT if x > hero_x else h.JOY_LEFT)
            if abs(hero_y - y) > near:
                keys.add(h.JOY_UP if y > hero_y else h.JOY_DOWN)
            self.play(1, keys)
        print(f"walk_to: didn't reach ({x:02X}, {y:02X}) from ({hero_x:02X}, {hero_y:02X}) in room "
              f"${int(self.ram[0x8A - 0x80]):02X} - {self.caption!r} at {self.frame / FPS:.1f} s", flush=True)
        return most

    def route(self, *points: tuple[int, int], most: int = 400) -> None:
        """walk_to each point in turn (around walls the straight line would hit)."""
        for x, y in points:
            self.walk_to(x, y, most)

    def use(self, look: str | None = None, cast: str | None = None, world: str | None = None,
            popup: bool = True) -> None:
        """Straight to a look, cast and world (None: leave as is), with the info pop-up as a key would
        show."""
        win = self.win
        win.look_key = look or win.look_key
        win.cast_key = cast or win.cast_key
        win.world_key = world or win.world_key
        win.compare = {"look": None, "cast": None, "world": None}
        if win.music:
            win.music.use_world(win.look.world)
            win.music_area = None
        if popup:
            win.now_showing.show()

    def switch(self, key: int, frames: int = 8) -> None:
        """Hold a console switch (h.JOY_SELECT / h.JOY_START) for a few frames, then let go."""
        self.play(frames, {key})

    def poke(self, values: dict[int, int]) -> None:
        """Set up a scene: write RAM ({address: value}). The next frame is the game's from there - shown
        as a cut, not a room scroll."""
        ram = self.ram
        if 0x8A in values:  # where the game bounces the hero back to after a wall: here, not the old room
            values = {0xE2: values[0x8A], 0xE3: values[0x8B], 0xE4: values[0x8C], **values}
        for addr, value in values.items():
            ram[addr - 0x80] = value
        self.win.prev_state = None
        # the 2600 sees walls by hardware collision with the picture it last drew - still the old room's
        # for a frame - so stand still while the new room is drawn
        self.play(2)
        if 0x8A in values and int(ram[0x8A - 0x80]) != values[0x8A]:
            print(f"poke: the hero didn't stay in room ${values[0x8A]:02X}", flush=True)

    def clear(self) -> None:
        """Every dragon, item and the bat out of the way (into the far red maze), the dragons dead, nothing
        carried - for a scene of its own."""
        for addr in (0xA4, 0xA9, 0xAE, 0xB3, 0xB6, 0xB9, 0xBC, 0xBF, 0xC2, 0xC5, 0xCB):
            self.ram[addr - 0x80] = 0x1D
        for dragon in (0xA4, 0xA9, 0xAE):  # dead, so they don't wander back in (a scene revives its own)
            self.ram[dragon + 4 - 0x80] = 1
        self.ram[0x9D - 0x80] = 0xA2
        self.ram[0xD0 - 0x80] = 0

    def card(self, lines: list[CardLine], seconds: float) -> None:
        """A full-screen title card: [(text, size, colour)], centred, top to bottom."""
        img = pygame.Surface((WIDTH, HEIGHT))
        img.fill(BACKGROUND)
        fonts: dict[int, pygame.font.Font] = {}
        heights = [mono(size, bold=True).get_linesize() + 18 for _, size, _ in lines]
        y = (HEIGHT - sum(heights)) // 2
        for (text, size, colour), line_height in zip(lines, heights):
            f = fonts.setdefault(size, mono(size, bold=True))
            rendered = f.render(text, True, colour)
            img.blit(rendered, ((WIDTH - rendered.get_width()) // 2, y))
            y += line_height
        still = pygame.surfarray.array3d(img).transpose(1, 0, 2)
        for i in range(int(seconds * FPS)):
            fade = min(1.0, i / 15, (seconds * FPS - i) / 15)
            self.emit((still * fade).astype(np.uint8), self.silence())

    # ---- frames -------------------------------------------------------------------------------------------

    def silence(self) -> Samples:
        return np.zeros((self.samples_for_frame(), 2), np.int16)

    def samples_for_frame(self) -> int:
        return round((self.frame + 1) * self.rate / FPS) - self.samples_done

    def step(self) -> None:
        """One frame of the app, as its run() loop does it, captured."""
        Clock.now = self.frame / FPS
        win = self.win
        win.step_game()
        if win.core.frame is None:
            return
        win.draw_pictures()
        win.show()
        canvas = pygame.surfarray.array3d(win.canvas).transpose(1, 0, 2)
        self.emit(self.compose(canvas), self.sound.take(self.samples_for_frame()))

    def compose(self, canvas: Picture) -> Picture:
        img = np.zeros((HEIGHT, WIDTH, 3), np.uint8)
        img[:] = BACKGROUND
        canvas_h, canvas_w = canvas.shape[:2]
        k = max(1, min(WIDTH // canvas_w, STAGE_H // canvas_h))
        if k > 1:
            canvas = canvas.repeat(k, 0).repeat(k, 1)
            canvas_h, canvas_w = canvas.shape[:2]
        if canvas_w > WIDTH or canvas_h > STAGE_H:  # too big: shrink smoothly
            shrink = min(WIDTH / canvas_w, STAGE_H / canvas_h)
            smaller = (int(canvas_w * shrink), int(canvas_h * shrink))
            canvas = np.array(Image.fromarray(canvas).resize(smaller, Image.Resampling.LANCZOS))
            canvas_h, canvas_w = canvas.shape[:2]
        y0, x0 = (STAGE_H - canvas_h) // 2, (WIDTH - canvas_w) // 2
        img[y0:y0 + canvas_h, x0:x0 + canvas_w] = canvas
        if self.caption:
            surf = pygame.Surface((WIDTH, HEIGHT - STAGE_H))
            surf.fill(BACKGROUND)
            rendered = self.font.render(self.caption, True, INK)
            left = (WIDTH - rendered.get_width()) // 2
            surf.blit(rendered, (left, (HEIGHT - STAGE_H - rendered.get_height()) // 2))
            img[STAGE_H:] = pygame.surfarray.array3d(surf).transpose(1, 0, 2)
        return img

    def emit(self, img: Picture, audio: Samples) -> None:
        if self.stills:
            if self.frame % self.stills == 0:
                Image.fromarray(img).save(os.path.join(self.out, f"{self.frame:05d}.png"))
        else:
            assert self.video is not None and self.video.stdin is not None   # started in __init__ (no stills)
            self.video.stdin.write(img.tobytes())
        self.audio.append(audio)
        self.samples_done += len(audio)
        self.frame += 1

    def finish(self) -> None:
        self.say(None)
        pcm = np.concatenate(self.audio)
        if self.stills:
            print(f"{self.frame} frames ({self.frame / FPS:.1f} s); stills in {self.out}")
            return
        assert self.video is not None and self.video.stdin is not None   # started in __init__ (no stills)
        self.video.stdin.close()
        self.video.wait()
        with wave.open(self.out + ".wav", "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(self.rate)
            w.writeframes(pcm.tobytes())
        subprocess.run([ffmpeg(), "-loglevel", "error", "-y", "-i", self.out + ".video.mp4",
                        "-i", self.out + ".wav", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-ar", "48000", "-shortest", self.out], check=True)
        os.remove(self.out + ".video.mp4")
        os.remove(self.out + ".wav")
        with open(os.path.splitext(self.out)[0] + ".srt", "w") as f:
            for i, (first, last, text) in enumerate(self.captions, 1):
                f.write(f"{i}\n{srt_time(first)} --> {srt_time(last)}\n{text}\n\n")
        print(f"{self.out}  {self.frame / FPS:.1f} s, captions in {os.path.splitext(self.out)[0]}.srt")


def srt_time(frame: int) -> str:
    millis = int(round(frame * 1000 / FPS))
    hours, minutes, secs = millis // 3600000, millis // 60000 % 60, millis // 1000 % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis % 1000:03d}"


STICK_UP, STICK_DOWN, STICK_LEFT, STICK_RIGHT, FIRE = h.JOY_UP, h.JOY_DOWN, h.JOY_LEFT, h.JOY_RIGHT, h.JOY_B


def script(reel: Reel) -> None:
    """The reel: about two minutes."""
    reel.card([("ADVENTURE FOREVER", 72, INK), ("Atari 2600 Adventure (1980), remastered live", 34, DIM)], 3)
    the_original(reel)
    the_looks(reel)
    casts_and_worlds(reel)
    the_game(reel)
    the_demo_packs(reel)
    the_grid(reel)
    the_win(reel)
    reel.card([("ADVENTURE FOREVER", 72, INK), ("Free and open source", 34, DIM),
               ("github.com/majonesmax/adventure-forever", 38, (232, 200, 72)),
               ("Adventure (c) 1980 Atari, by Warren Robinett. Bring your own ROM.", 26, DIM)], 6)
    reel.finish()


def the_original(reel: Reel) -> None:
    """The original, then what we read, then the remaster."""
    reel.press("next_view")
    reel.press("next_view")  # side by side -> look -> the 2600 alone
    reel.say("This is Atari 2600 Adventure (1980), running unmodified in an emulator.")
    reel.play(90)
    reel.switch(h.JOY_START)
    reel.play(40)
    reel.route((0x50, 0x16), (0x2C, 0x16))
    reel.press("next_view")  # -> the grid
    reel.say("Every frame, its 128 bytes of memory are read...")
    reel.route((0x22, 0x30), (0x22, 0x40))  # the gold key
    reel.say("...and the whole scene is drawn again, in a new look.")
    reel.route((0x22, 0x16), (0x50, 0x16))
    reel.press("next_view")  # -> side by side
    reel.say("Same game, same moves. Only the picture is new.")
    reel.play(140, {STICK_UP})  # the key opens the gate; into the castle
    reel.press("next_view")  # -> the look alone
    reel.clear()  # the key too: carried past the gate, it would open it again
    reel.poke({0x8A: 0x11, 0x8B: 0x50, 0x8C: 0x1C, 0xC8: 0x1C})  # back out in front of the castle, gate shut


def the_looks(reel: Reel) -> None:
    reel.say("Press L to change the look.")
    reel.route((0x20, 0x1C), most=60)
    for _look, line in (("snes", "SNES: 16-bit colour and a bigger cast."),
                        ("vga", "VGA: an early-90s PC game, 256 colours."),
                        ("paper", "Paper: crayon in a sketchbook."),
                        ("nes", "NES: where it started.")):
        reel.press("next_look")
        reel.say(line)
        reel.route((0x20, 0x50), (0x20, 0x1C), (0x40, 0x1C), most=60)  # clear of the gate


def casts_and_worlds(reel: Reel) -> None:
    reel.say("C changes the cast: who's in the game.")
    reel.press("next_cast")
    reel.route((0x20, 0x50), (0x20, 0x1C), most=80)
    reel.say("W changes the world: where it happens.")
    reel.press("next_world")
    reel.route((0x40, 0x1C), (0x20, 0x1C), (0x20, 0x40), most=60)
    reel.say("Any look shows any cast in any world.")
    for look, cast, world in (("snes", "classic", "pbj"), ("vga", "pbj", "classic"), ("paper", "pbj", "pbj"),
                              ("nes", "classic", "classic"), ("snes", "pbj", "pbj")):
        reel.use(look, cast, world)
        reel.route((0x40, 0x1C), (0x20, 0x1C), most=45)


def the_game(reel: Reel) -> None:
    """The game itself, staged: each scene set up in RAM, then played out by the real game."""
    reel.say("Fight dragons...")
    reel.use("snes", "classic", "classic", popup=False)
    reel.clear()
    reel.clear()
    # the sword in hand, the red dragon ahead
    reel.poke({0x8A: 0x02, 0x8B: 0x30, 0x8C: 0x30, 0xB6: 0x02, 0xB7: 0x38, 0xB8: 0x30, 0x9D: 0x09 * 9,
               0x9E: 8, 0x9F: 0, 0xA4: 0x02, 0xA5: 0x60, 0xA6: 0x30, 0xA8: 0})
    reel.play(24, {STICK_RIGHT})  # the sword meets the dragon
    reel.play(50, {STICK_LEFT})   # step back to see it
    reel.play(60)
    reel.say("...outwit the bat, who steals things...")
    reel.use("vga", "classic", "classic", popup=False)
    reel.clear()
    reel.poke({0x8A: 0x01, 0x8B: 0x50, 0x8C: 0x30, 0xBF: 0x01, 0xC0: 0x58, 0xC1: 0x30, 0x9D: 0x0B * 9,
               0x9E: 8, 0x9F: 0, 0xCB: 0x01, 0xCC: 0x90, 0xCD: 0x50, 0xCE: 0x9F, 0xCF: 7, 0xD0: 0,
               0xD1: 0})  # the key in hand, the bat coming
    reel.play(150)
    reel.say("...and find your way through the dark.")
    reel.use("paper", "sketchbook", "sketchbook", popup=False)
    reel.clear()
    reel.poke({0x8A: 0x13, 0x8B: 0x50, 0x8C: 0x3C})
    reel.route((0x20, 0x3C), (0x80, 0x3C), most=110)


def the_demo_packs(reel: Reel) -> None:
    reel.say("More packs are a download away: ORIENTATION, in the VGA look...")
    reel.use("vga", "orientation", "orientation")
    reel.clear()
    reel.poke({0x8A: 0x05, 0x8B: 0x18, 0x8C: 0x3C})
    reel.route((0x48, 0x3C), (0x48, 0x1C), most=90)
    reel.say("...and SKETCHBOOK, in the paper look.")
    reel.use("paper", "sketchbook", "sketchbook")
    reel.clear()
    reel.poke({0x8A: 0x0F, 0x8B: 0x50, 0x8C: 0x1C})
    reel.route((0x20, 0x1C), (0x20, 0x50), most=90)


def the_grid(reel: Reel) -> None:
    reel.use("nes", "classic", "classic", popup=False)
    reel.poke({0x8A: 0x02, 0x8B: 0x50, 0x8C: 0x30, 0x9D: 0xA2})
    reel.press("next_view")
    reel.press("next_view")  # -> the 2600 alone -> the grid
    reel.say("The grid: what you play, a comparison, the original and its live memory.")
    reel.route((0x80, 0x30), (0x30, 0x30), most=100)
    reel.press("compare_look")
    reel.say("Shift+L, C or W changes the comparison.")
    reel.route((0x80, 0x30), (0x30, 0x30), most=100)
    reel.press("next_view")  # -> side by side


def the_win(reel: Reel) -> None:
    reel.say("Bring the chalice home.")
    reel.use("snes", "pbj", "pbj", popup=False)
    reel.clear()
    reel.poke({0x8A: 0x12, 0x8B: 0x50, 0x8C: 0x18, 0xB9: 0x12, 0xBA: 0x58, 0xBB: 0x18, 0x9D: 0x10 * 9,
               0x9E: 8, 0x9F: 0})  # inside the gold castle, the chalice in hand
    reel.play(300, {STICK_UP})
    reel.say("H shows every key.")
    reel.press("toggle_help", then=210)
    reel.press("toggle_help")
    reel.say(None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--out", default=os.path.join(paths.SHOTS, "reel.mp4"))
    parser.add_argument("--stills", type=int, default=0,
                        help="save every Nth frame as a PNG instead of a video")
    args = parser.parse_args()
    out = os.path.join(paths.SHOTS, "reel_stills") if args.stills else args.out
    rom = os.path.join(paths.ROOT, "roms", "adventure.a26")
    script(Reel(rom, out, args.stills))


if __name__ == "__main__":
    main()
