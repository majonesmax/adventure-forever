"""play.py --check: the app runs itself for a few seconds and says whether it works - from the source, or
inside a built download (the way to check a build, on any system, without playing; GitHub's "Downloads"
workflow runs it on every build).

It shows the title, presses GAME RESET to start game 1 and walks, with the grid's looks drawing; then it saves
the grid view as a picture and says what it saw - printed, and in self-check.txt beside the picture (a built
Windows app has no console to print to). The sound is held silent throughout.
"""

import os

import numpy as np
import pygame

from engine import emulator as h
from engine import paths

STEPS = [("title", 60, ()), ("reset", 20, (h.JOY_START,)), ("started", 60, ()), ("walk", 90, (h.JOY_LEFT,))]
# (what, frames, joystick buttons held)


def run(window):
    """Run the checks on a GameWindow. True if all went well."""
    window.audio.mixer = lambda block: np.zeros_like(block)   # silent
    os.makedirs(paths.SCREENSHOTS, exist_ok=True)
    with open(os.path.join(paths.SCREENSHOTS, "self-check.txt"), "w") as log:
        def say(line):
            print(line, flush=True)
            log.write(line + "\n")
        say(f"{paths.APP_NAME} on {paths.SYSTEM}")
        return play(window, say)


def play(window, say):
    started_at = None
    for what, frames, held in STEPS:
        window.core.joy = set(held)
        for _ in range(frames):
            play_frame(window)
        if what == "started":
            started_at = window.state.hero
    window.core.joy = set()
    return report(window, say, started_at)


def play_frame(window):
    pygame.event.pump()   # keeps the window responsive; the check presses its own buttons
    window.step_game()
    if window.core.frame is not None:
        window.draw_pictures()
        window.show()


def report(window, say, started_at):
    state = window.state
    path = os.path.join(paths.SCREENSHOTS, "self-check.png")
    pygame.image.save(window.canvas, path)
    say(f"game {state.game}, room {state.room_num}, hero from {started_at} to {state.hero}")
    say(f"picture: {path}")
    ok = not state.on_title_screen and state.hero != started_at
    say("OK" if ok else "FAIL: the game didn't start, or the hero didn't move")
    return ok
