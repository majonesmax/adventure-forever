ADVENTURE FOREVER
=================

Atari 2600 Adventure (Warren Robinett, 1980) running unmodified in an emulator (Stella), with every
frame redrawn live from the game's 128 bytes of RAM - as an NES game or a Super NES one, with the
knight and dragons in brick castles or PBJ and friends in the candy kingdoms, or mixed. The 2600 picture runs alongside so you can compare.
Gameplay is 100% the original.

Needs an Apple Silicon Mac, and your own copy of the Adventure ROM (a 4 KB .a26 file): the first time
you start the app it asks for it once and remembers it.

FIRST LAUNCH
  The app isn't signed with an Apple developer ID, so macOS blocks it the first time:
    Right-click "Adventure Forever.app" -> Open -> Open.
  (Or: double-click, then System Settings -> Privacy & Security -> "Open Anyway".)
  After that it opens normally.

KEYS
  Arrows / Space   joystick / fire (drop item)
  Tab              GAME SELECT (games 1-3)
  Enter            GAME RESET (start)
  L                look: NES -> SNES
  C                cast: the knight -> PBJ and friends
  W                world: the brick castles -> the candy, ice and fire kingdoms
  I                show which look, cast and world are on screen
  V                view: side by side with the original -> remaster only -> 2600 only
                   -> 4-way grid (both remasters, the original and its live RAM)
  T                room-scroll transitions on/off
  M, - / =         music on/off, music volume
  N                next music source (your own music.json, if any -> the built-in songs)
  S                screenshot (saved to Pictures/Adventure Forever)
  R                record gameplay on/off (saved to Movies/Adventure Forever;
                   needs ffmpeg: brew install ffmpeg)
  P                pause        Esc  quit

The music is original chiptune written for this project.
