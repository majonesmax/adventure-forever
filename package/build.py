"""Build Adventure Forever for download, on the system it runs on (a Windows build has to be made on
Windows, and so on - PyInstaller can't cross-build).

Usage: python package/build.py [--with-rom] [--with-private]

  -> package/dist/Adventure-Forever-<system>-<processor>.zip  (.tar.gz on Linux), holding an
     "Adventure Forever" folder: the app (macOS: Adventure Forever.app; Windows: Adventure Forever.exe;
     Linux: the "Adventure Forever" program - with its files in _internal/), README.txt and licenses/.

  The public build has the public packs (packs/) and the built-in music, and asks for the player's ROM.
  --with-rom      bundles roms/adventure.a26 - for your own copies only, never for publishing.
  (Either makes a zip named ...-PERSONAL-do-not-publish.)
  --with-private  bundles private/: your packs (private/packs/, without their source/ folders), your
                  private/music.json and the music files it names, and private/README_extra.txt appended
                  to the README - personal builds only, never for publishing.

Needs: the requirements (pip install -r requirements.txt), the emulator core (python tools/get_core.py - run
for you if missing). The core is GPL-2.0: its licence and the exact source of the version bundled go into
the download (STELLA.txt).
"""

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from engine import paths  # noqa: E402

NAME = paths.APP_NAME
PKG = os.path.join(ROOT, "package")
STAGE, WORK, DIST = (os.path.join(PKG, folder) for folder in ("stage", "build", "dist"))
STELLA_SOURCE = "https://github.com/stella-emu/stella"
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
PROCESSORS = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}
Bundled = list[tuple[str, str]]   # PyInstaller's (source, destination) pairs


def stage_packs(src: str, dst: str) -> None:
    """Each pack's pack.json, cast/ and world/ (pictures and their .py); source/ stays behind."""
    for name in sorted(os.listdir(src)) if os.path.isdir(src) else []:
        pack = os.path.join(src, name)
        if not os.path.exists(os.path.join(pack, "pack.json")):
            continue
        os.makedirs(os.path.join(dst, name))
        shutil.copy(os.path.join(pack, "pack.json"), os.path.join(dst, name))
        for part in ("cast", "world"):
            if os.path.isdir(os.path.join(pack, part)):
                shutil.copytree(os.path.join(pack, part), os.path.join(dst, name, part),
                                ignore=shutil.ignore_patterns("__pycache__"))


def core_version() -> str:
    """The bundled Stella core's version, as it reports itself (e.g. "8.0_pre b52ccb02e")."""
    class Info(ctypes.Structure):
        _fields_ = [("name", ctypes.c_char_p), ("version", ctypes.c_char_p), ("extensions", ctypes.c_char_p),
                    ("need_fullpath", ctypes.c_bool), ("block_extract", ctypes.c_bool)]
    info = Info()
    ctypes.CDLL(paths.CORE).retro_get_system_info(ctypes.byref(info))
    return info.version.decode()


def stella_notice(version: str) -> str:
    commit = version.split()[-1] if " " in version else ""
    source = f"{STELLA_SOURCE}/tree/{commit}" if commit else STELLA_SOURCE
    return (f"This download includes the Stella emulator core (version {version}), which runs the game.\n"
            f"Stella is free software under the GNU General Public License, version 2 or later\n"
            f"(Stella-License-GPL-2.0.txt, Stella-Copyright.txt).\n\n"
            f"Its source code, for exactly this version: {source}\n"
            f"(the libretro core is built from src/os/libretro).\n\n"
            f"Adventure Forever itself is MIT-licensed (LICENSE); its art and music are CC BY 4.0\n"
            f"(LICENSE-ASSETS.md). Adventure is (c) 1980 Atari - not included; bring your own ROM.\n")


def icon() -> str | None:
    """The app icon for this system (macOS .icns, Windows .ico made from the preview PNG), or None."""
    if paths.SYSTEM == "macos":
        return os.path.join(PKG, "icon.icns")
    if paths.SYSTEM == "windows":
        from PIL import Image
        ico = os.path.join(STAGE, "icon.ico")
        Image.open(os.path.join(PKG, "icon_preview.png")).save(ico, sizes=ICO_SIZES)
        return ico
    return None


def options() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Adventure Forever for download on this system.")
    parser.add_argument("--with-rom", action="store_true",
                        help="bundle roms/adventure.a26 (personal builds only)")
    parser.add_argument("--with-private", action="store_true", help="bundle private/ (personal builds only)")
    return parser.parse_args()


def stage_private(data: Bundled, binaries: Bundled) -> None:
    """--with-private: the private packs, private/music.json and the music files it names (and the NSF
    player, if any) - into the stage, and onto PyInstaller's lists."""
    private = os.path.join(STAGE, "private")
    os.makedirs(private)
    stage_packs(os.path.join(paths.PRIVATE, "packs"), os.path.join(private, "packs"))
    config = os.path.join(paths.PRIVATE, "music.json")
    if os.path.exists(config):
        shutil.copy(config, private)
        with open(config) as config_file:
            music = json.load(config_file)
        for key, source in music.items():  # the music files it names
            music_file = not key.startswith("_") and (source.get("nsf") or source.get("file"))
            if music_file:
                data.append((os.path.join(ROOT, music_file), os.path.dirname(music_file)))
        from engine import music as MU
        gme = next((path for path in MU.LIB_PATHS if os.path.exists(path)), None)
        if gme:  # NSF playback
            binaries.append((gme, "lib"))
    data.append((private, "private"))


def pyinstaller_command(data: Bundled, binaries: Bundled) -> list[str]:
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
               "--log-level", "WARN", "--name", NAME, "--distpath", os.path.join(STAGE, "app"),
               "--workpath", WORK, "--specpath", WORK,
               "--exclude-module", "tkinter", "--exclude-module", "tools", "--exclude-module", "tests"]
    if paths.SYSTEM == "macos":
        command += ["--osx-bundle-identifier", "com.adventure-forever.app"]
    app_icon = icon()
    if app_icon:
        command += ["--icon", app_icon]
    separator = os.pathsep  # PyInstaller's "source<separator>destination" for --add-data
    for source, destination in data:
        command += ["--add-data", f"{source}{separator}{destination}"]
    for source, destination in binaries:
        command += ["--add-binary", f"{source}{separator}{destination}"]
    return command + [os.path.join(ROOT, "play.py")]


def assemble(with_private: bool) -> str:
    """The download's folder: the app, the README (+ private/README_extra.txt) and the licences."""
    folder = os.path.join(DIST, NAME)
    if paths.SYSTEM == "macos":
        os.makedirs(folder)
        shutil.move(os.path.join(STAGE, "app", f"{NAME}.app"), folder)
    else:  # the program at the top, its files in _internal/ beside it
        shutil.move(os.path.join(STAGE, "app", NAME), folder)
    with open(os.path.join(PKG, "README.txt")) as readme_file:
        readme = readme_file.read()
    extra = os.path.join(paths.PRIVATE, "README_extra.txt")
    if with_private and os.path.exists(extra):
        with open(extra) as extra_file:
            readme += "\n" + extra_file.read()
    newline = "\r\n" if paths.SYSTEM == "windows" else "\n"
    with open(os.path.join(folder, "README.txt"), "w", newline=newline) as readme_file:
        readme_file.write(readme)
    licences = os.path.join(folder, "licenses")
    shutil.copytree(os.path.join(PKG, "licenses"), licences)
    for licence in ("LICENSE", "LICENSE-ASSETS.md"):
        shutil.copy(os.path.join(ROOT, licence), licences)
    with open(os.path.join(licences, "STELLA.txt"), "w") as notice:
        notice.write(stella_notice(core_version()))
    return folder


def archive(folder: str, personal: bool) -> str:
    """The zip (macOS, Windows) or .tar.gz (Linux) to publish - or, personal, not to."""
    machine = platform.machine().lower()
    processor = PROCESSORS.get(machine, machine)
    label = "-PERSONAL-do-not-publish" if personal else ""
    base = os.path.join(DIST, f"Adventure-Forever-{paths.SYSTEM}-{processor}{label}")
    if paths.SYSTEM == "linux":
        out = base + ".tar.gz"
        with tarfile.open(out, "w:gz") as tar:
            tar.add(folder, arcname=NAME)
        return out
    if paths.SYSTEM == "macos":  # ditto keeps the .app's links and signature intact
        out = base + ".zip"
        subprocess.run(["ditto", "-c", "-k", "--keepParent", folder, out], check=True)
        return out
    return shutil.make_archive(base, "zip", DIST, NAME)


def main() -> None:
    args = options()
    if not os.path.exists(paths.CORE):
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "get_core.py")], check=True)
    for folder in (STAGE, WORK, DIST):
        shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(STAGE)
    stage_packs(os.path.join(ROOT, "packs"), os.path.join(STAGE, "packs"))
    data: Bundled = [(os.path.join(STAGE, "packs"), "packs"),
                     (os.path.join(ROOT, "shared", "fonts"), "shared/fonts"),
                     (os.path.join(ROOT, "engine", "palette_ntsc.json"), "engine")]
    binaries: Bundled = [(paths.CORE, "cores")]
    if args.with_rom:
        data.append((paths.ROM, "roms"))
    if args.with_private:
        stage_private(data, binaries)
    subprocess.run(pyinstaller_command(data, binaries), check=True)
    out = archive(assemble(args.with_private), personal=args.with_rom or args.with_private)
    print(f"{out}  ({os.path.getsize(out) // (1024 * 1024)} MB, Stella {core_version()})")


if __name__ == "__main__":
    main()
