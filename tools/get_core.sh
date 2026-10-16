#!/bin/zsh
# Download the Stella (Atari 2600) libretro core into cores/ - the emulator the game runs on (GPL-2.0,
# https://github.com/stella-emu/stella). Apple Silicon build from the libretro buildbot.
set -euo pipefail
cd "${0:A:h}/.."
mkdir -p cores/dl
url=https://buildbot.libretro.com/nightly/apple/osx/arm64/latest/stella_libretro.dylib.zip
curl -fL -o cores/dl/stella_libretro.dylib.zip "$url"
unzip -o -q cores/dl/stella_libretro.dylib.zip -d cores
ls -la cores/stella_libretro.dylib
