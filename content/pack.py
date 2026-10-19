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
from typing import Callable, TypeVar

from content.cast import Cast
from content.world import World

Part = TypeVar("Part", Cast, World)   # a cast or a world: what a pack's own cast.py / world.py extends


def custom(folder: str, filename: str, base: type[Part]) -> type[Part]:
    """The class in folder/filename (CustomCast / CustomWorld), else base. The folder is importable from it,
    so a world.py can keep helpers in modules beside it."""
    path = os.path.join(folder, filename)
    if not os.path.exists(path):
        return base
    if folder not in sys.path:
        sys.path.insert(0, folder)
    module_name = f"{os.path.basename(os.path.dirname(folder))}_{filename[:-3]}"  # e.g. pbj_world
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None   # a .py file that exists always has a loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "Custom" + base.__name__)


class Pack:
    """key, name, folder, cast (a Cast or None), world (a World or None)."""

    def __init__(self, folder: str, find: "Callable[[str], Pack] | None" = None):
        """find(key) -> another Pack, for a world that extends one."""
        self.folder = folder
        self.key: str = os.path.basename(os.path.normpath(folder))
        with open(os.path.join(folder, "pack.json")) as f:
            info = json.load(f)
        self.name: str = info.get("name", self.key.upper())
        cast_dir, world_dir = os.path.join(folder, "cast"), os.path.join(folder, "world")
        cast_info = {"name": self.name, **info.get("cast", {})}
        world_info = {"name": self.name, **info.get("world", {})}
        self.cast: Cast | None = None
        if os.path.exists(os.path.join(cast_dir, "hero_down_0.png")):
            self.cast = custom(cast_dir, "cast.py", Cast)(self.key, cast_dir, cast_info)
        self.world: World | None = None
        if "extends" in world_info:
            self.world = extended_world(find, world_info["extends"]).extended(self.key, world_info)
        elif os.path.isdir(world_dir) or "world" in info:
            self.world = custom(world_dir, "world.py", World)(self.key, world_dir, world_info)


def extended_world(find: "Callable[[str], Pack] | None", key: str) -> World:
    """The world a pack.json's "extends" names (ValueError if there's no such pack with a world)."""
    base = find(key).world if find is not None else None
    if base is None:
        raise ValueError(f"\"extends\": no pack {key!r} with a world to start from")
    return base
