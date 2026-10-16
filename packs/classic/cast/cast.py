"""The classic cast's wooden bridge, drawn in code to fill the bridge's box exactly: rails over the original's
two rail columns, planks across the walkway, posts at both ends (a stretched picture can't place the rails).
"""

import numpy as np

from content.cast import Cast
from shared.palettes import NES

K = 0x0F


class CustomCast(Cast):
    def bridge(self, height, width=None):
        return wooden_bridge(width or height, height)


def wooden_bridge(w, h):
    """Wooden bridge filling the original's box: rails over the original's two rail columns, planks across
    the walkway between them, posts at both ends (the original has ## blocks for 4 rows top and bottom)."""
    out = np.zeros((h, w, 4), np.uint8)
    rail_w = max(2, w // 8)
    l0, l1 = rail_w, 2 * rail_w            # left rail: original column 1 of 8
    r0, r1 = w - 2 * rail_w, w - rail_w    # right rail: column 6
    post_h = h // 6
    plank, dark, light = (*NES[0x27], 255), (*NES[0x07], 255), (*NES[0x37], 255)
    for y in range(h):
        out[y, l1:r0] = dark if y % 4 == 3 else plank   # planks, a dark gap every 4 px
        if y % 4 == 0:
            out[y, l1:r0] = light
    rail = (*NES[0x17], 255)
    out[:, l0:l1] = rail
    out[:, r0:r1] = rail
    out[:post_h, 0:l1] = rail
    out[:post_h, r0:w] = rail
    out[h - post_h:, 0:l1] = rail
    out[h - post_h:, r0:w] = rail
    # black outline around everything opaque
    fill = out[..., 3] > 0
    edge = fill & ~(np.roll(fill, 1, 0) & np.roll(fill, -1, 0) & np.roll(fill, 1, 1) & np.roll(fill, -1, 1))
    edge[0, :], edge[-1, :] = fill[0, :], fill[-1, :]
    out[edge] = (*NES[K], 255)
    return out
