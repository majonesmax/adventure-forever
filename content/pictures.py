"""Reading and writing a pack's pictures (PNG files <-> numpy RGBA arrays)."""

import os

import numpy as np
from PIL import Image

from shared.types import Picture

FLASH = (255, 0, 255)  # pixels of exactly this colour flash through the game's colours, like the chalice


def load(path: str, scale: int = 1) -> Picture:
    """A PNG -> RGBA, its pixels solid or clear (alpha under 128 is clear), shrunk by `scale` (each
    scale x scale block becomes its top-left pixel)."""
    picture = np.array(Image.open(path).convert("RGBA"))
    picture[..., 3] = np.where(picture[..., 3] >= 128, 255, 0)
    picture[picture[..., 3] == 0] = 0  # transparent is transparent, whatever colour an editor left behind
    if scale > 1:
        picture = picture[::scale, ::scale]
    return picture


def load_folder(folder: str, scale: int = 1) -> dict[str, Picture]:
    """{name: RGBA} for every PNG in `folder` (name = the file name without .png); {} without a folder."""
    if not os.path.isdir(folder):
        return {}
    pictures: dict[str, Picture] = {}
    for filename in sorted(os.listdir(folder)):
        if filename.endswith(".png"):
            pictures[filename[:-4]] = load(os.path.join(folder, filename), scale)
    return pictures


def save_folder(folder: str, pictures: dict[str, Picture]) -> None:
    """Write {name: RGBA or RGB array} as <folder>/<name>.png - how a pack's source/ scripts make its
    pictures."""
    folder = os.path.normpath(folder)
    os.makedirs(folder, exist_ok=True)
    for name, picture in pictures.items():
        pixels = np.ascontiguousarray(picture, np.uint8)
        mode = "RGBA" if pixels.shape[2] == 4 else "RGB"
        Image.fromarray(pixels, mode).save(os.path.join(folder, f"{name}.png"))
    print(f"{len(pictures)} pictures -> {folder}")
