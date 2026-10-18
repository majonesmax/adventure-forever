"""What's IN the game: casts (who) and worlds (where), which come in packs (folders) - the one place that
finds them. How the game is DRAWN is looks/ (the platforms); every look shows every cast in every world.

    packs(public)    {key: folder}: packs/ (classic, pbj first, then A-Z), then - unless public - the
                     folders in ADVENTURE_PACKS (packs from elsewhere, e.g. another repository), the packs the
                     player added (paths.USER_PACKS), then private/packs/
    install(path)    add the packs in a folder or .zip (a pack, a repository, a GitHub download) to USER_PACKS
    load(key)        a pack, loaded once (content/pack.py): .cast, .world
    casts(public)    keys of the packs with a cast, in the order C cycles them
    worlds(public)   keys of the packs with a world, in the order W cycles them

Packs need no code to be found: any folder in packs/ or private/packs/ with a pack.json. Packs kept somewhere
else (another repository) join by listing their folder in ADVENTURE_PACKS, several separated like PATH:
    ADVENTURE_PACKS=../shall-we-play-a-game/packs python play.py --pack orientation
"""

import os

from content.pack import Pack
from engine import paths

PUBLIC_PACKS = os.path.join(paths.ROOT, "packs")
PRIVATE_PACKS = os.path.join(paths.PRIVATE, "packs")  # git-ignored: personal packs never get published
EXTRA_PACKS = [os.path.abspath(folder) for folder in os.environ.get("ADVENTURE_PACKS", "").split(os.pathsep)
               if folder]
FIRST = ("classic", "pbj")  # the built-in packs lead the cycles
EXAMPLES = ("template",)  # reachable by name, left out of the cycles

_loaded = {}


def packs(public=False, examples=True):
    """{key: folder} - the public packs (built-in first), then the private ones unless public."""
    roots = [PUBLIC_PACKS]
    if not public:
        roots += [*EXTRA_PACKS, paths.USER_PACKS, PRIVATE_PACKS]
    found = {}
    for root in roots:
        if not os.path.isdir(root):
            continue
        names = [name for name in os.listdir(root) if os.path.exists(os.path.join(root, name, "pack.json"))]
        for name in sorted(names, key=cycle_order):
            if examples or name not in EXAMPLES:
                found.setdefault(name, os.path.join(root, name))  # the first root to have a key wins
    return found


def cycle_order(name):
    """The built-in packs first (classic, pbj), then A-Z."""
    if name in FIRST:
        return (0, FIRST.index(name), name)
    return (1, 0, name)


def is_private(key):
    """A pack that isn't the repository's own (private/packs/, or ADVENTURE_PACKS): kept out of --public
    builds and tests/golden_hashes.json."""
    return os.path.dirname(packs().get(key, "")) != PUBLIC_PACKS


def load(key):
    """The pack called `key`, loaded once (ValueError if there's none; a broken one raises its error)."""
    if key not in _loaded:
        folder = packs().get(key)
        if folder is None:
            raise ValueError(f"no pack called {key!r} (play.py --list shows them)")
        _loaded[key] = Pack(folder, find=load)
    return _loaded[key]


def _having(part, public, examples):
    out = []
    for key in packs(public, examples):
        try:
            if getattr(load(key), part) is not None:
                out.append(key)
        except Exception as err:  # a broken pack never stops the game
            print(f"pack {key} not loaded: {err}", flush=True)
    return out


def casts(public=False, examples=False):
    return _having("cast", public, examples)


def worlds(public=False, examples=False):
    return _having("world", public, examples)


def find_packs(folder, depth=3):
    """Every pack folder (one with a pack.json) in `folder`, looking down to `depth` levels."""
    if os.path.exists(os.path.join(folder, "pack.json")):
        return [folder]
    if depth == 0 or not os.path.isdir(folder):
        return []
    found = []
    for name in sorted(os.listdir(folder)):
        if not name.startswith(".") and os.path.isdir(os.path.join(folder, name)):
            found += find_packs(os.path.join(folder, name), depth - 1)
    return found


def install(path):
    """Copy the packs in `path` - a pack folder, a folder holding packs (e.g. a cloned repository), or a .zip
    of either (e.g. GitHub's "Download ZIP") - into the player's packs folder, replacing older copies.
    -> their keys. A pack can hold code (cast.py / world.py) that runs when it's shown: only add packs you
    trust."""
    import shutil
    import tempfile
    import zipfile
    with tempfile.TemporaryDirectory() as tmp:
        if os.path.isfile(path) and zipfile.is_zipfile(path):
            unzip_safely(path, tmp)
            path = tmp
        keys = []
        for pack in find_packs(path):
            key = os.path.basename(os.path.normpath(pack))
            target = os.path.join(paths.USER_PACKS, key)
            if os.path.abspath(pack) != os.path.abspath(target):
                shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(pack, target, ignore=shutil.ignore_patterns("__pycache__", ".git"))
            _loaded.pop(key, None)
            keys.append(key)
        return keys


def unzip_safely(zip_path, folder):
    """Unpack a .zip into `folder` - refusing it if any file would land outside the folder."""
    import zipfile
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            parts = member.replace("\\", "/").split("/")
            if os.path.isabs(member) or ".." in parts:
                raise ValueError(f"unsafe path in the zip: {member}")
        archive.extractall(folder)
