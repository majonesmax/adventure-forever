"""Download the Stella (Atari 2600) libretro core into cores/ - the emulator the game runs on (GPL-2.0,
https://github.com/stella-emu/stella), built for this computer by the libretro buildbot.

Usage: python tools/get_core.py            the core for this system
       python tools/get_core.py --force    download again even if it's there
"""

import io
import os
import platform
import sys
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root
from engine import paths

BUILDBOT = "https://buildbot.libretro.com/nightly"
BUILDS = {  # (system, processor) -> buildbot folder
    ("macos", "arm64"): "apple/osx/arm64",
    ("macos", "x86_64"): "apple/osx/x86_64",
    ("windows", "x86_64"): "windows/x86_64",
    ("linux", "x86_64"): "linux/x86_64",
}
SOURCE = "https://github.com/stella-emu/stella"


def processor():
    machine = platform.machine().lower()
    return {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(machine, machine)


def main():
    target = os.path.join(paths.ROOT, "cores", paths.CORE_FILE)
    if os.path.exists(target) and "--force" not in sys.argv:
        print(f"already there: {target}")
        return 0
    folder = BUILDS.get((paths.SYSTEM, processor()))
    if folder is None:
        print(f"no ready-made core for {paths.SYSTEM} on {processor()}; build Stella's libretro core from "
              f"{SOURCE} (src/os/libretro) and put {paths.CORE_FILE} in cores/")
        return 1
    url = f"{BUILDBOT}/{folder}/latest/{paths.CORE_FILE}.zip"
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as out:
            out.write(z.read(paths.CORE_FILE))  # only the core itself, whatever else the zip holds
    print(f"-> {target} ({os.path.getsize(target) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
