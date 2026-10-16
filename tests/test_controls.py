"""The keys are documented, everywhere: every key the window handles (app/window.py) is in app/controls.py - the
help panel's list - and every key in that list is in README.md's "Controls" table and the downloads'
package/README.txt. Fails with what's missing, so a new key can't go undocumented.

Usage: python tests/test_controls.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from app import controls  # noqa: E402
from app import window as W  # noqa: E402


def handled():
    """Every key name the window answers to (pygame.key.name style, "shift+l" for Shift+L)."""
    pygame.display.init()
    names = {pygame.key.name(k).lower() for k in (*W.JOYSTICK, *W.KEYS)}
    names |= {"shift+" + pygame.key.name(k).lower() for k in W.SHIFTED}
    return names | {"escape"}  # quit: handled in handle_input itself


def main():
    problems = []
    keys, listed = handled(), controls.covered()
    if keys - listed:
        problems.append(f"handled by the window but not in app/controls.py: {sorted(keys - listed)}")
    if listed - keys:
        problems.append(f"in app/controls.py but not handled by the window: {sorted(listed - keys)}")
    for doc in ("README.md", os.path.join("package", "README.txt")):
        with open(os.path.join(ROOT, doc), encoding="utf-8") as f:
            text = f.read()
        if doc == "README.md":
            text = text[text.find("## Controls"):]
        missing = [label for label in controls.labels() if label not in text]
        if missing:
            problems.append(f"{doc} doesn't list: {missing}")
    print("\n".join(problems) if problems else f"controls: all {len(keys)} keys documented in the help panel, "
                                                f"README.md and package/README.txt")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
