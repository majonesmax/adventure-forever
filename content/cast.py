"""A CAST: who's in the game - the hero, the three dragons, the bat, the items, the bridge, who announces the
win - as pictures in a pack's cast/ folder, plus the cast's lines in pack.json.

Every look shows every cast, adapting the pictures to its own rules (docs/platform-rules.md). Anything a cast
leaves out is drawn as the original 2600 graphic, so a cast can start with just a hero and grow.

THE PICTURES - PNGs with transparency, all optional except one hero picture:

    hero_down_0.png  hero_down_1.png      front view: standing, mid-stride          <- the only required file
    hero_up_0.png    hero_up_1.png        back view       (missing -> the front view)
    hero_right_0.png hero_right_1.png     side view       (missing -> the front view)
    hero_left_0.png  hero_left_1.png      (missing -> the side view mirrored)
                                          (a missing _1 stride frame -> the _0 picture)
    dragon_<pose>_<colour>.png            pose normal / roar / dead, colour red / yellow / green
    dragon_<pose>.png                     one design for all three colours
                                          (a missing dead pose -> the normal one upside down, as the 2600 does)
    bat_up.png  bat_down.png              the thief, flapping (missing down -> up)
    item_sword.png  item_magnet.png  item_chalice.png  item_key_gold.png  item_key_white.png  item_key_black.png
    bridge_top.png  bridge_middle.png  bridge_bottom.png
                                          the bridge, stretched to fit: top, then the middle repeated, then
                                          the bottom (the middle is usually one row)
    messenger.png  (or messenger_0.png, messenger_1.png, ...)
                                          who announces the win; several frames take turns (messenger_every)
    any other PNG                         e.g. a picture just for the title screen (title_cast)

Pixels are solid or clear (alpha under 128 counts as clear). Pixels of exactly FLASH (255, 0, 255, magenta)
flash through the game's colours, as the chalice does.

pack.json "cast" (every field optional):
    name             shown in --list and the grid view                    "PBJ AND FRIENDS"
    win_lines        three short lines (up to 18 characters) for the win  ["YOU WIN!", "THE CHALICE", "IS HOME!"]
    title_cast       pictures (file names without .png) in front of the title castle   ["hero_down_0", "messenger"]
    messenger_every  frames each messenger frame is shown                 16
    foot_gap         empty rows under the hero's feet in hero_*.png        0 or 1
    scale            the pictures are drawn this many times bigger than the room's pixels; the look shrinks
                     them. The rooms are 240x192: a hero about 16x26, dragons about 26x36, items about 16x8

Tricks pictures can't express (a bridge built in code): add cast.py to the cast/ folder, defining
`class CustomCast(Cast)` - it's made like a Cast and overrides any method below.
"""

import os

import numpy as np

from content import pictures as PIC

POSES = ("normal", "roar", "dead")
COLOURS = ("red", "yellow", "green")
ITEMS = {"sword": 0x09, "key_gold": 0x0B, "key_white": 0x0C, "key_black": 0x0D, "chalice": 0x10, "magnet": 0x11}


class Cast:
    """A cast, loaded. Looks use only the attributes and methods here.

    Sprites are numpy RGBA arrays (height, width, 4), alpha 0 = transparent; shared/pixelart.py can draw
    them as text art (each built-in pack's source/ folder keeps the text art its pictures were made from).
    """

    def __init__(self, key, folder, info):
        """key: the pack's; folder: its cast/ folder; info: pack.json's "cast" section."""
        self.key, self.folder = key, folder
        self.name = info.get("name", key.upper())
        self.win_lines = tuple(info.get("win_lines", ("YOU WIN!", "THE CHALICE", "IS HOME!")))
        self.title_names = info.get("title_cast", ["hero_down_0"])
        self.messenger_every = info.get("messenger_every", 16)
        self.foot_gap = info.get("foot_gap", 0)
        self.pictures = PIC.load_folder(folder, info.get("scale", 1))
        if "hero_down_0" not in self.pictures:
            raise ValueError(f"{folder}: a cast needs at least hero_down_0.png")

    def picture(self, name):
        return self.pictures.get(name)

    # ---- what looks ask for ----------------------------------------------------------------------------

    def hero(self):
        """{"down": [stand, stride], "up": [...], "right": [...], "left": [...]}."""
        p = self.pictures

        def frames(view, otherwise):
            if f"hero_{view}_0" not in p:
                return list(otherwise)
            stand = p[f"hero_{view}_0"]
            return [stand, p.get(f"hero_{view}_1", stand)]
        down = frames("down", None)
        right = frames("right", down)
        return {"down": down, "up": frames("up", down), "right": right,
                "left": frames("left", [f[:, ::-1] for f in right])}

    def villains(self):
        """{(pose, colour): sprite} for the three dragons; missing ones are drawn as the original."""
        p, out = self.pictures, {}
        for colour in COLOURS:
            for pose in POSES:
                spr = p.get(f"dragon_{pose}_{colour}", p.get(f"dragon_{pose}"))
                if spr is None and pose == "dead" and ("normal", colour) in out:
                    spr = out[("normal", colour)][::-1]  # upside down, as the 2600 does
                if spr is not None:
                    out[(pose, colour)] = spr
        return out

    def bat(self):
        """{"up": sprite, "down": sprite} - or {} for the original bat."""
        up = self.pictures.get("bat_up")
        return {} if up is None else {"up": up, "down": self.pictures.get("bat_down", up)}

    def items(self):
        """{object number: sprite} for whichever of ITEMS the cast draws."""
        return {n: self.pictures[f"item_{name}"] for name, n in ITEMS.items() if f"item_{name}" in self.pictures}

    def bridge(self, height, width=None):
        """The bridge `height` pixels long, centred in `width` if given; None = the original bridge."""
        top, mid, bottom = (self.pictures.get(f"bridge_{part}") for part in ("top", "middle", "bottom"))
        if mid is None:
            return None
        top = mid[:0] if top is None else top
        bottom = mid[:0] if bottom is None else bottom
        n = max(1, (height - top.shape[0] - bottom.shape[0] + mid.shape[0] - 1) // mid.shape[0])
        out = np.concatenate([top, np.tile(mid, (n, 1, 1)), bottom])
        if width and width > out.shape[1]:
            pad = width - out.shape[1]
            out = np.pad(out, ((0, 0), (pad // 2, pad - pad // 2), (0, 0)))
        return out

    def messenger(self, frame_no):
        """Who announces the win (beside the speech bubble), this frame; None = nobody."""
        frames = [self.pictures[k] for k in sorted(self.pictures) if k.startswith("messenger_")]
        if not frames:
            return self.pictures.get("messenger")
        return frames[(frame_no // self.messenger_every) % len(frames)]

    def title_cast(self):
        """The pictures standing in front of the castle on a title screen."""
        return [self.pictures[n] for n in self.title_names if n in self.pictures]
