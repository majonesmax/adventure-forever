"""VGA's colour rules: 256 colours on screen, each chosen from 262,144 (64 levels of red, green and blue).

A VGA game didn't have a fixed set of colours: it loaded its own 256 into the card, picked for its pictures.
So this look builds one palette per cast and world, the way the era's paint tools did (median cut):
  reserved  the 16 standard colours the card starts with, plus the look's own two - the menus and text
  cast      64 colours for the sprites and gates, so small sprites keep their colours next to big rooms
  world     the rest (174) for the rooms, including how the dark rooms look by torchlight, and any other
            scene the look shows (the VGA look's dim title castle)
Every screen is then drawn only in these 256: a VGA screen was a list of colour numbers, not colours.
"""

from collections.abc import Sequence

import numpy as np

from content.cast import Cast
from content.world import World
from engine import rooms as R
from shared import palettes as PAL
from shared.types import Floats, Picture, Rgb

Integers = np.ndarray   # an array of whole numbers: colour levels, counts, palette numbers

LEVELS = 64  # VGA's 6-bit colour: 64 levels a channel
CAST_COLOURS = 64
SIZE = 256
STANDARD_16 = [  # the colours a VGA card starts with (the EGA set)
    (0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170), (170, 0, 0), (170, 0, 170), (170, 85, 0),
    (170, 170, 170), (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255), (255, 85, 85),
    (255, 85, 255), (255, 255, 85), (255, 255, 255)]
DARK_ROOM_COLOUR = 0x08
TORCH_BANDS = (2 / 3, 1 / 3)  # the torch's dimmer rings (looks/base.py torch_lit)


def six_bit(rgb: Sequence[Rgb] | Sequence[Floats] | Floats) -> Integers:
    """8-bit colour -> the nearest of VGA's 64 levels a channel, back as 8-bit (0, 4, 8 ... 255)."""
    level = np.round(np.asarray(rgb, float) * (LEVELS - 1) / 255)
    return np.round(level * 255 / (LEVELS - 1)).astype(int)


def spread(colours: Floats) -> float:
    """How far apart a group's colours are, in its widest channel (0 for a single colour)."""
    return float(np.ptp(colours, axis=0).max())


def median_cut(colours: Floats, counts: Integers, how_many: int) -> Integers:
    """Pick `how_many` colours for a set of colours (n, 3) seen `counts` times each: split the group with
    the widest spread in two at its middle pixel, again and again, then average each group."""
    groups: list[Integers] = [np.arange(len(colours))]
    while len(groups) < how_many:
        spreads = [spread(colours[group]) for group in groups]
        widest = int(np.argmax(spreads))
        if spreads[widest] <= 0:
            break  # fewer colours than places for them
        group = groups.pop(widest)
        channel = int(np.argmax(np.ptp(colours[group], axis=0)))
        group = group[np.argsort(colours[group, channel])]
        running_total = np.cumsum(counts[group])
        middle = int(np.searchsorted(running_total, running_total[-1] / 2))
        middle = min(max(middle, 1), len(group) - 1)
        groups += [group[:middle], group[middle:]]
    chosen: list[Floats] = []
    for group in groups:
        weights = counts[group][:, None]
        chosen.append((colours[group] * weights).sum(axis=0) / weights.sum())
    return six_bit(chosen)


def counted(pixels: Picture) -> tuple[Floats, Integers]:
    """Pixels (n, 3) -> their distinct 6-bit colours and how often each is seen."""
    levels = np.round(np.asarray(pixels, float) * (LEVELS - 1) / 255).astype(int)
    colour_numbers = (levels[:, 0] * LEVELS + levels[:, 1]) * LEVELS + levels[:, 2]  # one number a colour
    times_seen = np.bincount(colour_numbers, minlength=LEVELS ** 3)
    seen = np.nonzero(times_seen)[0]
    red, green, blue = seen // (LEVELS * LEVELS), seen // LEVELS % LEVELS, seen % LEVELS
    colours = np.stack([red, green, blue], axis=1) * 255 / (LEVELS - 1)
    return colours, times_seen[seen]


def cast_pixels(cast: Cast, world: World) -> Picture:
    """Every solid pixel of the cast's pictures and the world's gates, and the colours the game's own
    graphics and flashing items use."""
    pictures = list(cast.pictures.values())
    pictures += [picture for name, picture in world.pictures.items() if name.startswith("gate")]
    pixels = [picture[picture[..., 3] >= 128][:, :3] for picture in pictures if picture.shape[2] == 4]
    game_colours = [*PAL.FLASH_CYCLE, *PAL.ORIGINAL_TO_NES.values(), PAL.BLACK]
    pixels.append(np.array([PAL.NES[colour] for colour in game_colours]))
    return np.concatenate(pixels)


def world_pixels(world: World, scenes: Sequence[Picture]) -> Picture:
    """Every pixel of every room, the dark rooms again as the torch's dimmer rings show them, and the
    look's other scenes (RGB pictures)."""
    rom = R.load_rom()
    pixels = [scene.reshape(-1, 3) for scene in scenes]
    for room_number in range(R.N_ROOMS):
        room = R.decode_room(rom, room_number)
        picture = world.room(room).reshape(-1, 3)
        pixels.append(picture)
        if room["colour"] == DARK_ROOM_COLOUR:
            pixels += [(picture * band).astype(np.uint8) for band in TORCH_BANDS]
    return np.concatenate(pixels)


class VgaPalette:
    """One cast-and-world's 256 colours, and a table from every VGA colour to the nearest of them."""

    def __init__(self, cast: Cast, world: World, own_colours: Sequence[Rgb], scenes: Sequence[Picture]):
        reserved = six_bit(STANDARD_16 + list(own_colours))
        cast_colours = median_cut(*counted(cast_pixels(cast, world)), CAST_COLOURS)
        world_share = SIZE - len(reserved) - len(cast_colours)
        world_colours = median_cut(*counted(world_pixels(world, scenes)), world_share)
        self.colours: Picture = np.concatenate([reserved, cast_colours, world_colours]).astype(np.uint8)
        self.nearest: Picture = self.lookup_table()

    def lookup_table(self) -> Picture:
        """For each of the 64 x 64 x 64 VGA colours, the number of the nearest palette colour."""
        every_level = np.arange(LEVELS)
        red, green, blue = np.meshgrid(every_level, every_level, every_level, indexing="ij")
        every_colour = np.stack([red, green, blue], axis=-1).reshape(-1, 3) * 255 / (LEVELS - 1)
        palette = self.colours.astype(np.float32)
        # the distance from colour c to palette colour p, squared, is |c|^2 - 2 c.p + |p|^2; |c|^2 is the same
        # for every p, so the nearest p is the one with the smallest |p|^2 - 2 c.p (one matrix multiply)
        palette_size = (palette ** 2).sum(axis=1)
        closeness = palette_size[None, :] - 2 * (every_colour.astype(np.float32) @ palette.T)
        return np.argmin(closeness, axis=1).astype(np.uint8).reshape(LEVELS, LEVELS, LEVELS)

    def show(self, rgb: Picture) -> Picture:
        """RGB pixels (..., 3) -> the same pixels in this palette's colours."""
        levels = (rgb.astype(np.uint16) * (LEVELS - 1) + 127) // 255  # 8-bit -> 6-bit, rounded
        numbers = self.nearest[levels[..., 0], levels[..., 1], levels[..., 2]]
        return self.colours[numbers]


palettes: dict[tuple[str, str], VgaPalette] = {}  # (cast, world) -> its palette: built once, shared


def palette_for(cast: Cast, world: World, own_colours: Sequence[Rgb],
                scenes: Sequence[Picture] = ()) -> VgaPalette:
    key = (cast.key, world.key)
    if key not in palettes:
        palettes[key] = VgaPalette(cast, world, own_colours, scenes)
    return palettes[key]
