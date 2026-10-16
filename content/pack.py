"""A PACK: a folder that brings a cast, a world, or both - the unit you copy, share and keep private.

    packs/<name>/                 (or private/packs/<name>/ - git-ignored, never published)
        pack.json                 {"name": ..., "cast": {...}, "world": {...}}
        cast/                     the cast's pictures (content/cast.py) [+ cast.py for tricks]
        world/                    the world's tiles (content/world.py) [+ world.py for tricks]
        source/                   optional: what the pictures were made from (text art, scripts)

A pack has a cast if cast/ has a hero picture, and a world if it has a world/ folder or its pack.json says
"world" (e.g. one that extends another pack's world).
"""

import importlib.util
import json
import os
import sys

from content.cast import Cast
from content.world import World


def custom(folder, filename, base):
    """The class in folder/filename (CustomCast / CustomWorld), else base. The folder is importable from it,
    so a world.py can keep helpers in modules beside it."""
    path = os.path.join(folder, filename)
    if not os.path.exists(path):
        return base
    if folder not in sys.path:
        sys.path.insert(0, folder)
    spec = importlib.util.spec_from_file_location(f"{os.path.basename(os.path.dirname(folder))}_{filename[:-3]}",
                                                  path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "Custom" + base.__name__)


class Pack:
    """key, name, folder, cast (a Cast or None), world (a World or None)."""

    def __init__(self, folder, find=None):
        """find(key) -> another Pack, for a world that extends one."""
        self.folder = folder
        self.key = os.path.basename(os.path.normpath(folder))
        with open(os.path.join(folder, "pack.json")) as f:
            info = json.load(f)
        self.name = info.get("name", self.key.upper())
        cast_dir, world_dir = os.path.join(folder, "cast"), os.path.join(folder, "world")
        cast_info = {"name": self.name, **info.get("cast", {})}
        world_info = {"name": self.name, **info.get("world", {})}
        self.cast = None
        if os.path.exists(os.path.join(cast_dir, "hero_down_0.png")):
            self.cast = custom(cast_dir, "cast.py", Cast)(self.key, cast_dir, cast_info)
        self.world = None
        if "extends" in world_info:
            self.world = find(world_info["extends"]).world.extended(self.key, world_info)
        elif os.path.isdir(world_dir) or "world" in info:
            self.world = custom(world_dir, "world.py", World)(self.key, world_dir, world_info)
