#!/bin/zsh
# Build "Adventure Forever.app" (Apple Silicon) + a zip.
# Usage: package/build_app.sh [--with-rom] [--with-private]
#   The app plays the NES and SNES looks with the public packs' casts and worlds (packs/) and the built-in music.
#   Without --with-rom it asks for adventure.a26 on first launch (Finder dialog) and remembers it.
#   --with-rom      bundles roms/adventure.a26 - for your own copies only, never for publishing.
#   --with-private  bundles private/: personal packs (private/packs/, without their source/ folders),
#                   private/music.json and the music files it names, private/README_extra.txt appended to
#                   the README - personal builds only, never for publishing.
# Needs cores/stella_libretro.dylib (tools/get_core.sh). libgme (brew install game-music-emu) is bundled if
# installed - it's only used for NSF music from a music.json.
set -euo pipefail
cd "${0:A:h}/.."
WITH_ROM=0; WITH_PRIVATE=0
for a in "$@"; do
  case $a in --with-rom) WITH_ROM=1;; --with-private) WITH_PRIVATE=1;; *) echo "unknown: $a"; exit 1;; esac
done
test -f cores/stella_libretro.dylib || { echo "cores/stella_libretro.dylib missing - run tools/get_core.sh"; exit 1; }

STAGE=package/stage; OUT=package/dist
rm -rf $STAGE package/build $OUT; mkdir -p $STAGE/lib $OUT

# the packs: pack.json, cast/ and world/ (pictures and their .py); source/ (how they were made) stays behind
stage_packs() {  # stage_packs <from> <to>
  for d in $1/*(/); do
    [[ -f $d/pack.json ]] || continue
    mkdir -p $2/${d:t}; cp $d/pack.json $2/${d:t}/
    for part in cast world; do
      [[ -d $d/$part ]] && { mkdir -p $2/${d:t}/$part; cp $d/$part/*.png(N) $d/$part/*.py(N) $2/${d:t}/$part/; }
    done
  done
}
mkdir -p $STAGE/packs; stage_packs packs $STAGE/packs

EXTRA=()
if [[ -f /opt/homebrew/lib/libgme.dylib ]]; then  # optional; give it a bundle-relative id
  cp -L /opt/homebrew/lib/libgme.dylib $STAGE/lib/libgme.dylib
  chmod u+w $STAGE/lib/libgme.dylib
  install_name_tool -id @rpath/libgme.dylib $STAGE/lib/libgme.dylib
  EXTRA+=(--add-binary "$PWD/$STAGE/lib/libgme.dylib:lib")
fi
if (( WITH_ROM )); then EXTRA+=(--add-data "$PWD/roms/adventure.a26:roms"); fi
if (( WITH_PRIVATE )); then  # loaded at run time from <app>/private (content.packs, music.load_configs)
  mkdir -p $STAGE/private/packs
  stage_packs private/packs $STAGE/private/packs
  [[ -f private/music.json ]] && cp private/music.json $STAGE/private/
  EXTRA+=(--add-data "$PWD/$STAGE/private:private")
  if [[ -f private/music.json ]]; then  # the music files the private config names
    for f in $(.venv/bin/python -c "import json; c=json.load(open('private/music.json')); print(' '.join(sorted({v.get('nsf') or v.get('file') for k, v in c.items() if not k.startswith('_') and (v.get('nsf') or v.get('file'))})))"); do
      EXTRA+=(--add-data "$PWD/$f:${f:h}")
    done
  fi
fi

.venv/bin/pyinstaller --noconfirm --clean --windowed --log-level WARN \
  --name "Adventure Forever" --osx-bundle-identifier com.adventure-forever.app \
  --icon "$PWD/package/icon.icns" \
  --distpath $OUT --workpath package/build --specpath package/build \
  --add-binary "$PWD/cores/stella_libretro.dylib:cores" \
  --add-data "$PWD/$STAGE/packs:packs" \
  --add-data "$PWD/engine/palette_ntsc.json:engine" \
  ${EXTRA[@]} \
  --exclude-module tkinter --exclude-module tools --exclude-module tests \
  play.py

APP="$OUT/Adventure Forever.app"
rm -rf "$OUT/Adventure Forever"  # PyInstaller's loose onedir copy - the .app already has everything
mkdir -p "$OUT/Adventure Forever"
mv "$APP" "$OUT/Adventure Forever/"; cp package/README.txt "$OUT/Adventure Forever/"
if (( WITH_PRIVATE )) && [[ -f private/README_extra.txt ]]; then
  cat private/README_extra.txt >> "$OUT/Adventure Forever/README.txt"
fi
ditto -c -k --keepParent "$OUT/Adventure Forever" "$OUT/Adventure-Forever.zip"
du -sh "$OUT/Adventure Forever" "$OUT/Adventure-Forever.zip"
