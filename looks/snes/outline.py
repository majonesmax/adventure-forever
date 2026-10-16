"""The SNES look's outline rule for sprites: a sprite's silhouette edge in a dark shade of the colour beside
it (DS-style coloured line art), and at most 15 colours (a SNES sprite palette)."""

import numpy as np
from PIL import Image

from shared.pixelart import shade, snes_rgb


def recolour_outline(spr, dark=0.45, max_colours=15):
    """Silhouette-edge pixels -> a dark shade of the fill colour next to them (DS-style coloured line art);
    interior dark pixels (eyes, mouths) keep their colour. Then cap the sprite at max_colours."""
    out = spr.copy()
    a = spr[..., 3] > 0
    pa = np.pad(a, 1)
    edge = a & ~(pa[:-2, 1:-1] & pa[2:, 1:-1] & pa[1:-1, :-2] & pa[1:-1, 2:])
    rgb = spr[..., :3].astype(int)
    lum = rgb @ [0.299, 0.587, 0.114]
    fill = a & (lum > 70)
    h, w = a.shape
    for y, x in zip(*np.nonzero(edge & (lum <= 70))):
        ys, xs = slice(max(0, y - 2), y + 3), slice(max(0, x - 2), x + 3)
        f = fill[ys, xs]
        if f.any():
            cols, counts = np.unique(rgb[ys, xs][f], axis=0, return_counts=True)
            out[y, x, :3] = snes_rgb(np.array(shade(cols[np.argmax(counts)], dark), np.uint8))
    # cap colours
    px = out[..., :3][a]
    if len(np.unique(px, axis=0)) > max_colours:
        q = Image.fromarray(px.reshape(1, -1, 3)).quantize(colors=max_colours, method=Image.Quantize.MEDIANCUT,
                                                            dither=Image.Dither.NONE)
        out[a, :3] = snes_rgb(np.array(q.convert("RGB"))[0])
    return out
