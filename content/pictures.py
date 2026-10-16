"""Reading and writing a pack's pictures (PNG files <-> numpy RGBA arrays)."""

import os

import numpy as np
from PIL import Image

FLASH = (255, 0, 255)  # pixels of exactly this colour flash through the game's colours, like the chalice


def load(path, scale=1):
    """A PNG -> RGBA, its pixels solid or clear (alpha under 128 is clear), shrunk by `scale` (each
    scale x scale block becomes its top-left pixel)."""
    im = np.array(Image.open(path).convert("RGBA"))
    im[..., 3] = np.where(im[..., 3] >= 128, 255, 0)
    im[im[..., 3] == 0] = 0  # transparent is transparent, whatever colour an editor left behind
    return im[::scale, ::scale] if scale > 1 else im


def load_folder(folder, scale=1):
    """{name: RGBA} for every PNG in `folder` (name = the file name without .png); {} if there's no folder."""
    if not os.path.isdir(folder):
        return {}
    return {f[:-4]: load(os.path.join(folder, f), scale) for f in sorted(os.listdir(folder)) if f.endswith(".png")}


def save_folder(folder, pictures):
    """Write {name: RGBA or RGB array} as <folder>/<name>.png - how a pack's source/ scripts make its pictures."""
    folder = os.path.normpath(folder)
    os.makedirs(folder, exist_ok=True)
    for name, picture in pictures.items():
        a = np.ascontiguousarray(picture, np.uint8)
        Image.fromarray(a, "RGBA" if a.shape[2] == 4 else "RGB").save(os.path.join(folder, f"{name}.png"))
    print(f"{len(pictures)} pictures -> {folder}")
