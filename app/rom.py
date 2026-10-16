"""Finding the player's Adventure ROM (never included - bring your own).

Looked for in order: roms/adventure.a26 next to the code (or bundled in a personal app build), then the copy
remembered in the user's folder; failing both, a Finder dialog asks once and a copy is kept for next time.
"""

import os
import shutil
import subprocess

from engine import paths

ROM_SIZE = 4096  # Adventure is a 4 KB cartridge


def find_rom():
    """Path to the ROM, or None if the player cancels the dialog."""
    remembered = os.path.join(paths.USER_DIR, "adventure.a26")
    for path in (paths.ROM, remembered):
        if os.path.exists(path):
            return path
    ask = ('POSIX path of (choose file with prompt "Adventure needs the Atari 2600 Adventure ROM '
           '(a 4 KB .a26 or .bin file). Pick it once and it will be remembered.")')
    picked = subprocess.run(["osascript", "-e", ask], capture_output=True, text=True).stdout.strip()
    if not picked:
        return None
    if os.path.getsize(picked) != ROM_SIZE:
        subprocess.run(["osascript", "-e", 'display alert "That doesn\'t look like Adventure" message '
                        '"The Adventure ROM is exactly 4096 bytes."'])
        return None
    os.makedirs(paths.USER_DIR, exist_ok=True)
    shutil.copyfile(picked, remembered)
    return remembered
