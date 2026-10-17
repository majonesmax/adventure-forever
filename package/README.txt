ADVENTURE FOREVER
=================

Atari 2600 Adventure (Warren Robinett, 1980) running unmodified in an emulator (Stella), with every
frame redrawn live from the game's 128 bytes of RAM - as an NES game or a Super NES one, with the
knight and dragons in brick castles or PBJ and friends in the candy kingdoms, or mixed. The 2600
picture runs alongside so you can compare. Gameplay is 100% the original.

You need your own copy of the Adventure ROM (a 4 KB .a26 or .bin file). The first time the game
starts, it asks you to drag the ROM onto its window, and remembers it after that. Once it's
running, press H for every key.

STARTING IT
  macOS     Open "Adventure Forever.app". The app isn't signed with an Apple developer ID, so the
            first time macOS refuses to open it. Then open System Settings -> Privacy & Security,
            scroll down to '"Adventure Forever" was blocked', click "Open Anyway" and confirm.
            After that it opens normally. (Or, in Terminal, in this folder:
              xattr -dr com.apple.quarantine "Adventure Forever.app"  )
  Windows   Open "Adventure Forever.exe". The app isn't signed, so the first time Windows may show
            "Windows protected your PC": click "More info" -> "Run anyway".
  Linux     Run the "Adventure Forever" program in this folder. If there's no sound, install your
            distribution's PortAudio package (e.g. libportaudio2).

KEYS (in the game, H shows them all)
  H                help: every key
  Arrows / Space   joystick / fire (drop item)
  Tab              GAME SELECT (games 1-3)
  Enter            GAME RESET (start)
  L                look: NES -> SNES -> VGA (early-90s PC) -> paper (crayon)
  C                cast: the knight -> PBJ and friends
  W                world: the brick castles -> the candy, ice and fire kingdoms
  I                show which look, cast and world are on screen
  V                view: side by side with the original -> remaster only -> 2600 only
                   -> 4-way grid: your game over a comparison (the other console, same cast
                   and world), the original and its live RAM
  Shift+L/C/W      the grid's comparison: its own look, cast or world
  F                fullscreen on/off (or resize the window: the picture keeps its shape)
  T                room-scroll transitions on/off
  M, - / =         music on/off, music volume
  N                next music source (your own music.json, if any -> the built-in songs)
  S                screenshot (saved to your Pictures folder, in "Adventure Forever")
  R                record gameplay on/off (saved to your Movies / Videos folder, in "Adventure
                   Forever"; needs ffmpeg installed: https://ffmpeg.org/download.html)
  D                debug line: game speed (frames per second), room, render time
  P                pause
  Esc              quit (or close the help)

ADDING PACKS
  A pack is a new cast, world (and soundtrack) - like the demos at
  https://github.com/majonesmax/shall-we-play-a-game . Download it (on GitHub: Code -> Download ZIP)
  and drag the zip or its folder onto the game window: it's copied into your packs folder and shown.
  The packs folder is beside the remembered ROM:
    macOS     ~/Library/Application Support/Adventure Forever/packs
    Windows   %APPDATA%\Adventure Forever\packs
    Linux     ~/.local/share/Adventure Forever/packs
  Packs can contain code, so only add packs from people you trust.

The music is original chiptune written for this project. Licences: licenses/ (the game is MIT, its
art and music CC BY 4.0; the Stella emulator is GPL - licenses/STELLA.txt says where its source is).
