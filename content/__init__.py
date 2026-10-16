"""What's IN the game: casts (who) and worlds (where), which come in packs (folders) - the one place that
finds them. How the game is DRAWN is looks/ (the platforms); every look shows every cast in every world.

    packs(public)    {key: folder}: packs/ (classic, pbj first, then A-Z), then private/packs/ unless public
    load(key)        a pack, loaded once (content/pack.py): .cast, .world
    casts(public)    keys of the packs with a cast, in the order C cycles them
    worlds(public)   keys of the packs with a world, in the order W cycles them

Packs need no code to be found: any folder in packs/ or private/packs/ with a pack.json.
"""

import os

from content.pack import Pack
from engine import paths

PUBLIC_PACKS = os.path.join(paths.ROOT, "packs")
PRIVATE_PACKS = os.path.join(paths.PRIVATE, "packs")  # git-ignored: personal packs never get published
FIRST = ("classic", "pbj")  # the built-in packs lead the cycles
EXAMPLES = ("template",)  # reachable by name, left out of the cycles

_loaded = {}


def packs(public=False, examples=True):
    """{key: folder} - the public packs (built-in first), then the private ones unless public."""
    found = {}
    for root in (PUBLIC_PACKS,) if public else (PUBLIC_PACKS, PRIVATE_PACKS):
        if not os.path.isdir(root):
            continue
        names = [d for d in os.listdir(root) if os.path.exists(os.path.join(root, d, "pack.json"))]
        for d in sorted(names, key=lambda d: (d not in FIRST, FIRST.index(d) if d in FIRST else 0, d)):
            if examples or d not in EXAMPLES:
                found.setdefault(d, os.path.join(root, d))
    return found


def is_private(key):
    return os.path.dirname(packs().get(key, "")) == PRIVATE_PACKS


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
