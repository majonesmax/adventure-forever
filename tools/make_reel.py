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

W, H, FPS = 1920, 1080, 60
STAGE_H = 960                       # the app's picture goes in the top 1920x960; captions below
BG = (11, 11, 20)
INK, DIM = (236, 236, 244), (150, 150, 170)
READ_FRAMES = int(2.6 * 60)         # every caption stays up at least this long...
READ_SPEED = 18                     # ...and longer ones at this many characters a second


class Clock:
    """The video's clock: the info pop-up and the help panel ask it the time instead of the wall."""
    now = 0.0

    @classmethod
    def perf_counter(cls):
        return cls.now


class CapturedAudio:
    """Stands in for the sound card (engine/emulator.AudioOut): keeps the emulator's samples for the frame
    being made. The reel mixes them with the music itself, a frame's worth at a time."""

    def __init__(self, rate, mixer=None, **_):
        self.rate, self.mixer, self.pending = rate, mixer, []
        self.tap, self.expect, self.missing, self.dropped, self.xruns = None, True, 0, 0, 0

    def push(self, samples):
        self.pending.append(samples)

    def take(self, n):
        """Exactly n samples for this frame: the emulator's (silence while paused or scrolling) + the music."""
        sfx = np.concatenate(self.pending) if self.pending else np.zeros((0, 2), np.int16)
        self.pending = []
        block = np.zeros((n, 2), np.int16)
        block[:min(n, len(sfx))] = sfx[:n]
        return self.mixer(block) if self.mixer else block


class Reel:
    def __init__(self, rom, out, stills=0):
        NS.time = Clock                                  # the pop-ups fade on the video's clock
        h.AudioOut = CapturedAudio                       # no sound card: the reel mixes the sound itself
        REC.Recorder.__init__ = lambda self, *a, **k: setattr(self, "active", False)  # never records
        WIN.SCALE, WIN.SOLO_SCALE = 4, 4                 # every view fits 1920x960 at its native size
        self.win = WIN.GameWindow(rom, look_key="nes", public=True)
        # the public packs, then the demos from ADVENTURE_PACKS - never private ones
        extra = [k for k in content.packs() if os.path.dirname(content.packs()[k]) in content.EXTRA_PACKS]
        self.win.cast_keys += [k for k in extra if content.load(k).cast]
        self.win.world_keys += [k for k in extra if content.load(k).world]
        self.out, self.stills, self.frame = out, stills, 0
        self.rate = self.win.audio.rate
        self.samples_done = 0
        self.captions, self.caption, self.caption_from = [], None, 0
        self.font, self.small = mono(40, bold=True), mono(26)
        self.audio = []
        self.video = None
        if not stills:
            self.video = subprocess.Popen(
                [REC.find_ffmpeg(), "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                 "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                 "-pix_fmt", "yuv420p", out + ".video.mp4"], stdin=subprocess.PIPE)
        else:
            os.makedirs(out, exist_ok=True)

    # ---- the script's verbs -----------------------------------------------------------------------------

    def say(self, text=None):
        """The caption from now on (None: none). The one before stays up long enough to read: the game
        carries on, nothing pressed, until it has."""
        if self.caption:
            need = max(READ_FRAMES, int(len(self.caption) / READ_SPEED * FPS))
            if self.frame - self.caption_from < need:
                self.play(need - (self.frame - self.caption_from))
        if self.caption:
            self.captions.append((self.caption_from, self.frame, self.caption))
        self.caption, self.caption_from = text, self.frame

    def play(self, frames, keys=()):
        """Run the game for `frames` frames with these joystick directions held (h.JOY_*)."""
        for _ in range(frames):
            self.win.core.joy.clear()
            self.win.core.joy.update(keys)
            self.step()

    def press(self, command, then=0):
        """A window command, as its key would (a GameWindow method name: "next_look", "next_view"...)."""
        getattr(self.win, command)()
        self.play(then)

    def walk_to(self, x, y, most=600, near=2):
        """Walk the hero toward (x, y) in the game's units (y counts up) - stops there, or after `most`
        frames (a wall in the way). Returns the frames it took."""
        for i in range(most):
            hx, hy = int(self.win.core.ram[0x8B - 0x80]), int(self.win.core.ram[0x8C - 0x80])
            if abs(hx - x) <= near and abs(hy - y) <= near:
                return i
            keys = set()
            if abs(hx - x) > near:
                keys.add(h.JOY_RIGHT if x > hx else h.JOY_LEFT)
            if abs(hy - y) > near:
                keys.add(h.JOY_UP if y > hy else h.JOY_DOWN)
            self.play(1, keys)
        print(f"walk_to: didn't reach ({x:02X}, {y:02X}) from ({hx:02X}, {hy:02X}) in room "
              f"${int(self.win.core.ram[0x8A - 0x80]):02X} - {self.caption!r} at {self.frame / FPS:.1f} s", flush=True)
        return most

    def route(self, *points, most=400):
        """walk_to each point in turn (around walls the straight line would hit)."""
        for x, y in points:
            self.walk_to(x, y, most)

    def use(self, look=None, cast=None, world=None, popup=True):
        """Straight to a look, cast and world (None: leave as is), with the info pop-up as a key would show."""
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

    def switch(self, key, frames=8):
        """Hold a console switch (h.JOY_SELECT / h.JOY_START) for a few frames, then let go."""
        self.play(frames, {key})

    def poke(self, values):
        """Set up a scene: write RAM ({address: value}). The next frame is the game's from there - shown
        as a cut, not a room scroll."""
        ram = self.win.core.ram
        if 0x8A in values:  # where the game bounces the hero back to when he hits a wall: here, not the old room
            values = {0xE2: values[0x8A], 0xE3: values[0x8B], 0xE4: values[0x8C], **values}
        for addr, v in values.items():
            ram[addr - 0x80] = v
        self.win.prev_st = None
        # the 2600 sees walls by hardware collision with the picture it last drew - still the old room's
        # for a frame - so stand still while the new room is drawn
        self.play(2)
        if 0x8A in values and int(ram[0x8A - 0x80]) != values[0x8A]:
            print(f"poke: the hero didn't stay in room ${values[0x8A]:02X}", flush=True)

    def clear(self):
        """Every dragon, item and the bat out of the way (into the far red maze), the dragons dead, nothing
        carried - for a scene of its own."""
        for addr in (0xA4, 0xA9, 0xAE, 0xB3, 0xB6, 0xB9, 0xBC, 0xBF, 0xC2, 0xC5, 0xCB):
            self.win.core.ram[addr - 0x80] = 0x1D
        for dragon in (0xA4, 0xA9, 0xAE):  # dead, so they don't wander back in (a scene revives its own)
            self.win.core.ram[dragon + 4 - 0x80] = 1
        self.win.core.ram[0x9D - 0x80] = 0xA2
        self.win.core.ram[0xD0 - 0x80] = 0

    def card(self, lines, seconds):
        """A full-screen title card: [(text, size, colour)], centred, top to bottom."""
        img = pygame.Surface((W, H))
        img.fill(BG)
        fonts = {}
        heights = [mono(s, bold=True).get_linesize() + 18 for _, s, _ in lines]
        y = (H - sum(heights)) // 2
        for (text, size, colour), lh in zip(lines, heights):
            f = fonts.setdefault(size, mono(size, bold=True))
            r = f.render(text, True, colour)
            img.blit(r, ((W - r.get_width()) // 2, y))
            y += lh
        still = pygame.surfarray.array3d(img).transpose(1, 0, 2)
        for i in range(int(seconds * FPS)):
            fade = min(1.0, i / 15, (seconds * FPS - i) / 15)
            self.emit((still * fade).astype(np.uint8), self.silence())

    # ---- frames -------------------------------------------------------------------------------------------

    def silence(self):
        return np.zeros((self.samples_for_frame(), 2), np.int16)

    def samples_for_frame(self):
        n = round((self.frame + 1) * self.rate / FPS) - self.samples_done
        return n

    def step(self):
        """One frame of the app, as its run() loop does it, captured."""
        Clock.now = self.frame / FPS
        win = self.win
        win.step_game()
        if win.core.frame is None:
            return
        win.draw_pictures()
        win.show()
        canvas = pygame.surfarray.array3d(win.canvas).transpose(1, 0, 2)
        self.emit(self.compose(canvas), win.audio.take(self.samples_for_frame()))

    def compose(self, canvas):
        img = np.zeros((H, W, 3), np.uint8)
        img[:] = BG
        ch, cw = canvas.shape[:2]
        k = max(1, min(W // cw, STAGE_H // ch))
        if k > 1:
            canvas = canvas.repeat(k, 0).repeat(k, 1)
            ch, cw = canvas.shape[:2]
        if cw > W or ch > STAGE_H:  # too big: shrink smoothly
            s = min(W / cw, STAGE_H / ch)
            canvas = np.array(Image.fromarray(canvas).resize((int(cw * s), int(ch * s)), Image.LANCZOS))
            ch, cw = canvas.shape[:2]
        y0, x0 = (STAGE_H - ch) // 2, (W - cw) // 2
        img[y0:y0 + ch, x0:x0 + cw] = canvas
        if self.caption:
            surf = pygame.Surface((W, H - STAGE_H))
            surf.fill(BG)
            r = self.font.render(self.caption, True, INK)
            surf.blit(r, ((W - r.get_width()) // 2, (H - STAGE_H - r.get_height()) // 2))
            img[STAGE_H:] = pygame.surfarray.array3d(surf).transpose(1, 0, 2)
        return img

    def emit(self, img, audio):
        if self.stills:
            if self.frame % self.stills == 0:
                Image.fromarray(img).save(os.path.join(self.out, f"{self.frame:05d}.png"))
        else:
            self.video.stdin.write(img.tobytes())
        self.audio.append(audio)
        self.samples_done += len(audio)
        self.frame += 1

    def finish(self):
        self.say(None)
        pcm = np.concatenate(self.audio)
        if self.stills:
            print(f"{self.frame} frames ({self.frame / FPS:.1f} s); stills in {self.out}")
            return
        self.video.stdin.close()
        self.video.wait()
        with wave.open(self.out + ".wav", "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(self.rate)
            w.writeframes(pcm.tobytes())
        subprocess.run([REC.find_ffmpeg(), "-loglevel", "error", "-y", "-i", self.out + ".video.mp4",
                        "-i", self.out + ".wav", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-ar", "48000", "-shortest", self.out], check=True)
        os.remove(self.out + ".video.mp4")
        os.remove(self.out + ".wav")
        with open(os.path.splitext(self.out)[0] + ".srt", "w") as f:
            for i, (a, b, text) in enumerate(self.captions, 1):
                f.write(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n\n")
        print(f"{self.out}  {self.frame / FPS:.1f} s, captions in {os.path.splitext(self.out)[0]}.srt")


def srt_time(frame):
    ms = int(round(frame * 1000 / FPS))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


UP, DOWN, LEFT, RIGHT, FIRE = h.JOY_UP, h.JOY_DOWN, h.JOY_LEFT, h.JOY_RIGHT, h.JOY_B


def script(r):
    """The reel: about two minutes."""
    r.card([("ADVENTURE FOREVER", 72, INK), ("Atari 2600 Adventure (1980), remastered live", 34, DIM)], 3)

    # the original, then what we read, then the remaster
    r.press("next_view")
    r.press("next_view")  # side by side -> look -> the 2600 alone
    r.say("This is Atari 2600 Adventure (1980), running unmodified in an emulator.")
    r.play(90)
    r.switch(h.JOY_START)
    r.play(40)
    r.route((0x50, 0x16), (0x2C, 0x16))
    r.press("next_view")  # -> the grid
    r.say("Every frame, its 128 bytes of memory are read...")
    r.route((0x22, 0x30), (0x22, 0x40))  # the gold key
    r.say("...and the whole scene is drawn again, in a new look.")
    r.route((0x22, 0x16), (0x50, 0x16))
    r.press("next_view")  # -> side by side
    r.say("Same game, same moves. Only the picture is new.")
    r.play(140, {UP})  # the key opens the gate; into the castle
    r.press("next_view")  # -> the look alone
    r.clear()  # the key too: carried past the gate, it would open it again
    r.poke({0x8A: 0x11, 0x8B: 0x50, 0x8C: 0x1C, 0xC8: 0x1C})  # back out in front of the castle, its gate shut

    # looks
    r.say("Press L to change the look.")
    r.route((0x20, 0x1C), most=60)
    for look, line in (("snes", "SNES: 16-bit colour and a bigger cast."),
                       ("vga", "VGA: an early-90s PC game, 256 colours."),
                       ("paper", "Paper: crayon in a sketchbook."),
                       ("nes", "NES: where it started.")):
        r.press("next_look")
        r.say(line)
        r.route((0x20, 0x50), (0x20, 0x1C), (0x40, 0x1C), most=60)  # clear of the gate

    # casts and worlds
    r.say("C changes the cast: who's in the game.")
    r.press("next_cast")
    r.route((0x20, 0x50), (0x20, 0x1C), most=80)
    r.say("W changes the world: where it happens.")
    r.press("next_world")
    r.route((0x40, 0x1C), (0x20, 0x1C), (0x20, 0x40), most=60)
    r.say("Any look shows any cast in any world.")
    for look, cast, world in (("snes", "classic", "pbj"), ("vga", "pbj", "classic"), ("paper", "pbj", "pbj"),
                              ("nes", "classic", "classic"), ("snes", "pbj", "pbj")):
        r.use(look, cast, world)
        r.route((0x40, 0x1C), (0x20, 0x1C), most=45)

    # the game itself, staged: each scene set up in RAM, then played out by the real game
    r.say("Fight dragons...")
    r.use("snes", "classic", "classic", popup=False)
    r.clear()
    r.clear()
    r.poke({0x8A: 0x02, 0x8B: 0x30, 0x8C: 0x30, 0xB6: 0x02, 0xB7: 0x38, 0xB8: 0x30, 0x9D: 0x09 * 9, 0x9E: 8,
            0x9F: 0, 0xA4: 0x02, 0xA5: 0x60, 0xA6: 0x30, 0xA8: 0})  # sword in hand, the red dragon ahead
    r.play(24, {RIGHT})  # the sword meets the dragon
    r.play(50, {LEFT})   # step back to see it
    r.play(60)
    r.say("...outwit the bat, who steals things...")
    r.use("vga", "classic", "classic", popup=False)
    r.clear()
    r.poke({0x8A: 0x01, 0x8B: 0x50, 0x8C: 0x30, 0xBF: 0x01, 0xC0: 0x58, 0xC1: 0x30, 0x9D: 0x0B * 9, 0x9E: 8,
            0x9F: 0, 0xCB: 0x01, 0xCC: 0x90, 0xCD: 0x50, 0xCE: 0x9F, 0xCF: 7, 0xD0: 0, 0xD1: 0})  # the key in hand, the bat coming
    r.play(150)
    r.say("...and find your way through the dark.")
    r.use("paper", "sketchbook", "sketchbook", popup=False)
    r.clear()
    r.poke({0x8A: 0x13, 0x8B: 0x50, 0x8C: 0x3C})
    r.route((0x20, 0x3C), (0x80, 0x3C), most=110)

    # the demo packs
    r.say("More packs are a download away: ORIENTATION, in the VGA look...")
    r.use("vga", "orientation", "orientation")
    r.clear()
    r.poke({0x8A: 0x05, 0x8B: 0x18, 0x8C: 0x3C})
    r.route((0x48, 0x3C), (0x48, 0x1C), most=90)
    r.say("...and SKETCHBOOK, in the paper look.")
    r.use("paper", "sketchbook", "sketchbook")
    r.clear()
    r.poke({0x8A: 0x0F, 0x8B: 0x50, 0x8C: 0x1C})
    r.route((0x20, 0x1C), (0x20, 0x50), most=90)

    # the grid
    r.use("nes", "classic", "classic", popup=False)
    r.poke({0x8A: 0x02, 0x8B: 0x50, 0x8C: 0x30, 0x9D: 0xA2})
    r.press("next_view")
    r.press("next_view")  # -> the 2600 alone -> the grid
    r.say("The grid: what you play, a comparison, the original and its live memory.")
    r.route((0x80, 0x30), (0x30, 0x30), most=100)
    r.press("compare_look")
    r.say("Shift+L, C or W changes the comparison.")
    r.route((0x80, 0x30), (0x30, 0x30), most=100)
    r.press("next_view")  # -> side by side

    # the win
    r.say("Bring the chalice home.")
    r.use("snes", "pbj", "pbj", popup=False)
    r.clear()
    r.poke({0x8A: 0x12, 0x8B: 0x50, 0x8C: 0x18, 0xB9: 0x12, 0xBA: 0x58, 0xBB: 0x18, 0x9D: 0x10 * 9,
            0x9E: 8, 0x9F: 0})  # inside the gold castle, the chalice in hand
    r.play(300, {UP})
    r.say("H shows every key.")
    r.press("toggle_help", then=210)
    r.press("toggle_help")
    r.say(None)
    r.card([("ADVENTURE FOREVER", 72, INK), ("Free and open source", 34, DIM),
            ("github.com/majonesmax/adventure-forever", 38, (232, 200, 72)),
            ("Adventure (c) 1980 Atari, by Warren Robinett. Bring your own ROM.", 26, DIM)], 6)
    r.finish()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=os.path.join(paths.SHOTS, "reel.mp4"))
    ap.add_argument("--stills", type=int, default=0, help="save every Nth frame as a PNG instead of a video")
    args = ap.parse_args()
    out = os.path.join(paths.SHOTS, "reel_stills") if args.stills else args.out
    rom = os.path.join(paths.ROOT, "roms", "adventure.a26")
    script(Reel(rom, out, args.stills))


if __name__ == "__main__":
    main()
