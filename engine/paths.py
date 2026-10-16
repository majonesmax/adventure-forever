"""Where things live. Everything else asks here instead of working out paths from its own location.

In development ROOT is the repository; in the packaged app (package/build_app.sh) it is the app bundle's
data folder, which is read-only - so files the game writes go to the user's own folders instead.
"""

import os
import sys

APP_NAME = "Adventure Forever"
FROZEN = getattr(sys, "frozen", False)
ROOT = getattr(sys, "_MEIPASS", None) if FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROM = os.path.join(ROOT, "roms", "adventure.a26")
CORE = os.path.join(ROOT, "cores", "stella_libretro.dylib")
PRIVATE = os.path.join(ROOT, "private")      # personal packs and music config - git-ignored, never published
SHOTS = os.path.join(ROOT, "shots")          # development output (screenshots, sheets)

USER_DIR = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}") if FROZEN else ROOT
SCREENSHOTS = os.path.expanduser(f"~/Pictures/{APP_NAME}") if FROZEN else os.path.join(SHOTS, "play")
RECORDINGS = os.path.expanduser(f"~/Movies/{APP_NAME}") if FROZEN else os.path.join(ROOT, "recordings")
