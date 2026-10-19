"""Where things live. Everything else asks here instead of working out paths from its own location.

In development ROOT is the repository; in a packaged app (package/build.py) it is the app's bundled data
folder, which is read-only - so files the game writes go to the player's own folders instead, in the usual
places for their system (USER_DIR, SCREENSHOTS, RECORDINGS below).
"""

import os
import sys

APP_NAME = "Adventure Forever"
FROZEN = getattr(sys, "frozen", False)
if FROZEN:  # a packaged app: everything bundled is unpacked here
    ROOT: str = getattr(sys, "_MEIPASS")   # a packaged app always has it
else:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYSTEM = {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")

ROM = os.path.join(ROOT, "roms", "adventure.a26")
CORE_FILES = {"macos": "stella_libretro.dylib", "windows": "stella_libretro.dll",
              "linux": "stella_libretro.so"}
CORE_FILE = CORE_FILES[SYSTEM]
CORE = (os.environ.get("ADVENTURE_CORE")  # another core to try, e.g. a newer Stella build
        or os.path.join(ROOT, "cores", CORE_FILE))  # the emulator (tools/get_core.py downloads it)
PRIVATE = os.path.join(ROOT, "private")      # personal packs and music config - git-ignored, never published
SHOTS = os.path.join(ROOT, "shots")          # development output (screenshots, sheets)
FONTS = os.path.join(ROOT, "shared", "fonts")


def _home(*parts: str) -> str:
    return os.path.join(os.path.expanduser("~"), *parts)


def _user_folder(xdg_name: str, fallback: str) -> str:
    """A Linux user folder (Pictures, Videos) as the desktop names it (~/.config/user-dirs.dirs), else
    ~/fallback."""
    try:
        with open(_home(".config", "user-dirs.dirs")) as f:
            for line in f:
                if line.startswith(f"XDG_{xdg_name}_DIR="):
                    return os.path.expandvars(line.split("=", 1)[1].strip().strip('"'))
    except OSError:
        pass
    return _home(fallback)


if not FROZEN:  # development: everything inside the repository
    USER_DIR, SCREENSHOTS, RECORDINGS = ROOT, os.path.join(SHOTS, "play"), os.path.join(ROOT, "recordings")
elif SYSTEM == "macos":
    USER_DIR = _home("Library", "Application Support", APP_NAME)
    SCREENSHOTS, RECORDINGS = _home("Pictures", APP_NAME), _home("Movies", APP_NAME)
elif SYSTEM == "windows":
    USER_DIR = os.path.join(os.environ.get("APPDATA") or _home("AppData", "Roaming"), APP_NAME)
    SCREENSHOTS, RECORDINGS = _home("Pictures", APP_NAME), _home("Videos", APP_NAME)
else:
    USER_DIR = os.path.join(os.environ.get("XDG_DATA_HOME") or _home(".local", "share"), APP_NAME)
    SCREENSHOTS = os.path.join(_user_folder("PICTURES", "Pictures"), APP_NAME)
    RECORDINGS = os.path.join(_user_folder("VIDEOS", "Videos"), APP_NAME)

# packs the player adds (dropped on the game window, or copied in): beside the remembered ROM in a packaged
# app, private/packs/ when running from source (git-ignored, like the player's own)
USER_PACKS = os.path.join(USER_DIR, "packs") if FROZEN else os.path.join(PRIVATE, "packs")
