"""The pbj world's grass: a 32x32 ground tile for the meadows and the candy kingdom's lawns, in four
greens. D = dark, G and g = mid, L = light.

It was first generated with Stable Diffusion; this text art is the source now.

Usage: python packs/pbj/source/grass.py   -> packs/pbj/world/grass.png
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))  # the repo root
from content.pictures import save_folder
from shared.pixelart import from_ascii

COLOURS = {"D": (57, 115, 41), "G": (99, 140, 41), "g": (99, 156, 41), "L": (107, 156, 41)}

GRASS = """
LLLLgDDgLLLLLLLLLggLLLLLLLLLLLGG
LLLLLgLLLLLLLLLLLLLLLLLLggLLLLLL
LGGgGLLLLLLLLLLLLLLLLLLgDDGgGggL
GDDDDgLLLggLLLLLLLggLLLGDDDDDDgL
GDDDDGLLGGDGGGgLLLgggLLLGDggDDgL
LGDDGgLgDDDDGDgLLLLggLLLLLLLLgLL
LLLLLLLLDDDDDDDgLLGGGgLLLLLLLLLL
LLLLLLLLLGgGDDgLLLGDGLLLLLLgGLgL
LLLLLLLLLLLLLLLLLLLLLLLGGgLGGGgL
LLLLLLLLLLLLLLLLggLLLLLGGLLgDDgL
LLLLLLLLLLLLLLLgDDDDgLLGGgLLggLL
LLLLLLgGgLLLLLLGDDDDgLLgGLLLLLLL
LLLLLLLGGgLLLgggGDGgLLLLLLLLLLLL
LLLLLLLggggDggGgLLLLLLLLLLLLLLLL
LLLLLLgDDDDDDgggLLLLLLLLLLLLLLLL
LLLLLLLDDDDDDGLLLLLLgGGgLGGGGLLL
LLggLLLgDDDDDDLLLLLLLGGgGDDDDgLL
gGDDGLLLLgDDggLLLgggLLLLLDDDDgLg
gDDDDgLLLLLLLLLLgGGgLLLLLLggLLLL
LGDGgLLLLLLLLLLLLgggLLLLLLLLLLLL
LLLLLLLLLLLLLLLLLggLLLLLLLLLLLLL
LLLLLLLLLLLLggggGGGGGDggLLLLLLLg
LLLLLLLLLLLLgDgDDGGDDDDDgLLGgLgL
LLLLLgLLLLLLLLLDDDDGDDDDgLLGGggg
LLLLLGLLLLLLLLLLGGDDDDGgLLLLGDDD
LLLLLGGGgLLLLLLLLLLggggLLLLLGDDD
LLLLLLgggLLLLLLLLLLLLLLLggLLLGDg
gLLLLgGgLLgGGGGggDLLLLGgDGDgLLLL
LLLggGDGLGDDDDDDDDDggDDGDDDGLLLL
LLLggLgLLgDDDGGDDDDDgDDDDDDgLgGg
LLLggLLLLLgGDDDDDDDgLGDDDGgLLgDG
LggGDGgGGgLLLggggLLLLLLggLLLLLgL"""


def pictures():
    return {"grass": from_ascii(GRASS, COLOURS)[..., :3]}


if __name__ == "__main__":
    save_folder(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "world"), pictures())
