"""Cut a gameplay video from a recorder.py take: 1920x1080, 60 fps, H.264 + AAC (plays anywhere).

  1. Each stream is resampled to constant 60 fps on the WALL clock (log.jsonl 't'), so it lines up with
     audio.wav (recorded in real time) even where the game stalled. Pixel art scales with nearest-neighbour.
  2. The edit decision list - <take>/edit.json, written for each take - keeps time ranges of it; inside
     each, the layout follows the player's own view/version switches from the log (side by side, single,
     2600, grid), except forced layouts (e.g. a finale with two looks' win screens side by side).
  3. Captions, pane labels, title and end cards use the game's own pixel font (hud.py).
  4. Segments render separately (PCM audio); jump cuts dip through black, view switches cut straight;
     then one concat, where the audio is encoded once. The audio is pulled earlier by the take's own measured
     lag (measure_audio_lead), or edit.json's "audio_lead".

Usage: python make_video.py recordings/<take> [-o out.mp4]

edit.json:
  {"keep": [[from, to], ...],                       source seconds on the wall clock (log.jsonl 't')
   "force": [[from, to, "finale_<look>"], ...],     a finale = NES and <look> side by side
   "captions": [[at, seconds, "TEXT"], ...],        the pixel font has A-Z 0-9 and , - ! ' . ? : < >
   "title": [["TEXT", scale, [r, g, b], y], ...], "end": [...],    the title and end cards
   "names": {"<look key>": "PANE LABEL"},           labels for looks beyond the built-in ones
   "grid16": "<look key>"}                          the grid's lower look, for takes that didn't log it
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Any

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, as a script
from shared import hud as HUD
from app import recorder as REC
from shared.types import Rgb

Line = tuple[str, int, Rgb, int]               # a card's line: (text, scale, colour, y)
Placement = tuple[str, int, int, int, int]     # (stream, x, y, width, height)
Tag = tuple[str, int, int]                     # a pane label: (text, x, y)
Segment = tuple[float, float, str, bool, bool]   # (from, to, layout, fade in, fade out)
Part = tuple[float, float, str]                # a stretch of a kept range in one layout: (from, to, layout)
Caption = tuple[float, float, str]             # (at, seconds, text)

WIDTH, HEIGHT, FPS = 1920, 1080, 60
BACKGROUND = (11, 11, 20)
KEY = (1, 2, 3)  # transparent colour for overlay PNGs
CAPTION_COLOUR, CAPTION_Y, CAPTION_SCALE = (255, 236, 140), 1032, 3
DIP = 0.25       # seconds of fade through black at a jump cut (and of sound fading in or out there)
CUT = 0.03       # ...and of the sound's fade at a straight cut, so it doesn't click
STREAM_SIZE = {**REC.STREAMS, "ram": REC.RAM_SIZE}  # + the take's other looks (meta.json)
NAMES = {"nes": "NES REMASTER", "snes": "SNES REMASTER",
         "16bit": "16-BIT REMASTER", "forever": "16-BIT REMASTER"}  # the SNES look's old keys, in older takes

# the edit decision list: filled from <take>/edit.json by load_edit()
KEEP: list[tuple[float, float]] = []
FORCE: list[tuple[float, float, str]] = []
CAPTIONS: list[Caption] = []
GRID16 = "16bit"  # takes before the grid16 log entry
TITLE: list[Line] = [("ADVENTURE", 6, (236, 174, 212), 330),
                     ("ATARI 2600 - 1980 - WARREN ROBINETT", 3, (232, 232, 240), 470),
                     ("REMASTERED", 3, (232, 200, 72), 540)]
END: list[Line] = [("ADVENTURE BY WARREN ROBINETT, ATARI 1980", 3, (232, 232, 240), 380),
                   ("A FAN PROJECT - NOT FOR SALE", 2, (236, 174, 212), 560)]
ENVELOPE_RATE = 200   # the loudness envelope's steps a second (5 ms each)


def measure_audio_lead(take: str) -> float | None:
    """How late the take's audio is: for every sound the log saw start, find its onset in audio.wav (the
    2600's effects are far louder than the music) and take the median offset. None if too few found."""
    import wave
    with wave.open(os.path.join(take, "audio.wav")) as w:
        rate = w.getframerate()
        stereo = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2)
        mono = stereo.astype(np.float32).mean(axis=1)
    hop = rate // ENVELOPE_RATE  # 5 ms envelope
    env = np.sqrt(np.convolve(mono ** 2, np.ones(hop) / hop, mode="same"))[::hop]
    offsets: list[float] = []
    with open(os.path.join(take, "log.jsonl")) as f:
        for line in f:
            row = json.loads(line)
            if any(e.startswith("SOUND") for e in row.get("events", [])):
                onset = sound_onset(env, row["t"])
                if onset is not None:
                    offsets.append(onset)
    return float(np.clip(np.median(offsets), 0, 0.6)) if len(offsets) >= 3 else None


def sound_onset(env: np.ndarray, logged: float) -> float | None:
    """How long after `logged` (seconds) a sound starts in the loudness envelope, or None if none does."""
    window_start = int((logged - 0.3) * ENVELOPE_RATE)
    window_end = int((logged + 1.0) * ENVELOPE_RATE)
    window = env[window_start:window_end]
    base = np.median(env[max(0, window_start - ENVELOPE_RATE):window_start]) if window_start > 0 else 0
    hit = np.nonzero(window > max(base * 2.2, 6000))[0]
    if window_start >= 0 and hit.size:
        return (window_start + hit[0]) / ENVELOPE_RATE - logged
    return None


def load_edit(take: str) -> None:
    global KEEP, FORCE, CAPTIONS, GRID16, TITLE, END, AUDIO_LEAD
    with open(os.path.join(take, "edit.json")) as f:
        edit = json.load(f)
    with open(os.path.join(take, "meta.json")) as f:
        STREAM_SIZE.update({k: tuple(size) for k, size in json.load(f)["streams"].items()})
    KEEP = [tuple(kept) for kept in edit["keep"]]
    FORCE = [tuple(forced) for forced in edit.get("force", [])]
    CAPTIONS = [tuple(caption) for caption in edit.get("captions", [])]
    GRID16 = edit.get("grid16", GRID16)
    TITLE = card_lines(edit.get("title", TITLE))
    END = card_lines(edit.get("end", END))
    NAMES.update(edit.get("names", {}))
    lead = edit.get("audio_lead", measure_audio_lead(take))
    if lead is not None:
        AUDIO_LEAD = lead
    print(f"audio lead {AUDIO_LEAD:.3f} s", flush=True)


def card_lines(lines: list[Any]) -> list[Line]:
    """A card's lines from edit.json: their colours as tuples."""
    return [(text, scale, tuple(colour), y) for text, scale, colour, y in lines]


AUDIO_LEAD = 0.15  # sounds come ~0.15-0.35 s after the picture (the game's audio buffer); measured per take
MIN_SEG = 0.6  # view flashes shorter than this (cycling V past a view) keep the previous layout


def run(cmd: list[str], timeout: int = 120, tries: int = 4) -> None:
    """ffmpeg with -nostdin (it otherwise listens to the terminal and can freeze under a script) and one
    filter thread; a run that stalls anyway (ffmpeg 8 occasionally deadlocks on many-input overlay graphs -
    the same command finishes in ~1 s on a retry) is killed and retried."""
    full = [cmd[0], "-nostdin", "-filter_threads", "1", *cmd[1:]]
    for attempt in range(1, tries + 1):
        try:
            subprocess.run(full, check=True, stdin=subprocess.DEVNULL, timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            print(f"  ffmpeg stalled ({timeout} s) - retry {attempt}/{tries - 1}", flush=True)
    raise RuntimeError("ffmpeg kept stalling: " + " ".join(cmd[:12]))


def text_png(lines: list[Line], path: str, size: tuple[int, int] = (WIDTH, HEIGHT),
             background: Rgb | None = None) -> None:
    """lines: (text, scale, rgb, y). background None = transparent overlay."""
    img = np.zeros((size[1], size[0], 3), np.uint8)
    img[:] = background if background is not None else KEY
    for text, scale, rgb, y in lines:
        x = (size[0] - HUD.text_width(text, scale)) // 2
        HUD.draw_text(img, text, x, y, rgb, scale=scale, shadow=(0, 0, 0))
    if background is None:
        alpha = np.where((img == KEY).all(axis=2), 0, 255).astype(np.uint8)
        Image.fromarray(np.dstack([img, alpha])).save(path)
    else:
        Image.fromarray(img).save(path)


def tag_overlay(tags: list[Tag], path: str) -> None:
    """Small pane labels: (text, x, y) with a dark box."""
    img = np.zeros((HEIGHT, WIDTH, 3), np.uint8)
    img[:] = KEY
    for text, x, y in tags:
        w = HUD.text_width(text, 2)
        img[y - 6:y + 20, x - 8:x + w + 6] = (0, 0, 0)
        HUD.draw_text(img, text, x, y, (232, 232, 240), scale=2, shadow=None)
    rgba = np.dstack([img, np.where((img == KEY).all(axis=2), 0, 230).astype(np.uint8)])
    Image.fromarray(rgba).save(path)


def layout(name: str) -> tuple[list[Placement], list[Tag]]:
    """name: both_<look> / solo_<look> / 2600 / grid_<top look>_<bottom look> (or grid_<bottom>) /
    finale_<look> -> (placements [(stream, x, y, w, h)], tags [(text, x, y)])."""
    kind, _, rem = name.partition("_")
    label = NAMES.get(rem, rem.upper())
    if name.startswith("both"):
        return [(rem, 64, 60, 1024, 960), ("a2600", 1176, 312, 640, 456)], \
               [(label, 64, 24), ("ATARI 2600 - 1980", 1176, 276)]
    if kind == "solo":
        return [(rem, 448, 60, 1024, 960)], [(label, 448, 24)]
    if name == "2600":
        return [("a2600", 320, 70, 1280, 912)], [("ATARI 2600 - 1980", 320, 34)]
    if kind == "grid":
        return grid_layout(rem)
    if kind == "finale":
        return [("nes", 160, 170, 768, 720), (rem, 992, 170, 768, 720)], \
               [("NES REMASTER", 160, 134), (label, 992, 134)]
    raise ValueError(name)


def grid_layout(looks: str) -> tuple[list[Placement], list[Tag]]:
    """As in play.py: playing over the comparison left, the original over its RAM right. looks:
    <top>_<bottom>, or just <bottom> in older takes (NES on top)."""
    top, _, bottom = looks.partition("_") if "_" in looks else ("nes", "", looks)
    top_label, label = NAMES.get(top, top.upper()), NAMES.get(bottom, bottom.upper())
    lower = "compare" if "compare" in STREAM_SIZE else bottom  # takes since 1.2.2: the pane as shown
    return [(top, 448, 60, 512, 480), (lower, 448, 540, 512, 480), ("a2600", 960, 117, 512, 365),
            ("ram", 960, 540, 512, 480)], \
           [(top_label, 448, 24), ("ATARI 2600 - 1980", 960, 24),        # bottom row: side margins (the
            (label, 448 - HUD.text_width(label, 2) - 24, 548),          # captions own the bottom)
            ("INTERNALS", 1472 + 24, 548)]


def cfr_streams(take: str, work: str) -> dict[str, str]:
    """Each stream -> constant 60 fps on the wall clock (repeat/skip frames by log 't')."""
    with open(os.path.join(take, "log.jsonl")) as f:
        times = np.array([json.loads(line)["t"] for line in f])
    n_out = int(times[-1] * FPS) + 1
    src_for = np.searchsorted(times, np.arange(n_out) / FPS, side="right") - 1
    src_for = np.clip(src_for, 0, len(times) - 1)
    if not os.path.exists(os.path.join(take, "ram.mp4")):
        REC.render_ram_video(take)
    out: dict[str, str] = {}
    for name, size in STREAM_SIZE.items():
        dst = os.path.join(work, f"{name}_cfr.mp4")
        out[name] = dst
        if not os.path.exists(dst):
            crf = "0" if name != "ram" else "12"   # lossless, but for the RAM pane's text
            resample(os.path.join(take, f"{name}.mp4"), dst, size, src_for, crf)
    return out


def resample(source: str, dst: str, size: tuple[int, int], src_for: np.ndarray, crf: str) -> None:
    """Re-time one stream: output frame n is source frame src_for[n]."""
    w, h = size
    dec = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", source, "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-", "-c:v", "libx264rgb",
                            "-preset", "ultrafast", "-crf", crf, dst], stdin=subprocess.PIPE)
    assert dec.stdout is not None and enc.stdin is not None   # both opened as pipes
    frame_bytes, cur_i = w * h * 3, -1
    cur: bytes | None = None
    for want in src_for:
        while cur_i < want:
            buf = dec.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            cur, cur_i = buf, cur_i + 1
        assert cur is not None   # the stream has at least one frame
        enc.stdin.write(cur)
    enc.stdin.close()
    enc.wait()
    dec.stdout.close()
    dec.wait()


def layout_at(rows: list[dict[str, Any]], times: np.ndarray, moment: float) -> str:
    """The layout at `moment` (seconds): a forced one, else the logged view and look."""
    for force_start, force_end, name in FORCE:
        if force_start <= moment < force_end:
            return name
    row = rows[max(0, np.searchsorted(times, moment, side="right") - 1)]
    view, look = row["view"], row["look"]
    return {"both": f"both_{look}", "nes": f"solo_{look}", "look": f"solo_{look}", "2600": "2600",
            "grid": f"grid_{row.get('grid_top', 'nes')}_{row.get('grid16', GRID16)}"}[view]


def plan(take: str) -> list[Segment]:
    """KEEP ranges -> segments [(t0, t1, layout, fade_in, fade_out)] following the logged view/version."""
    with open(os.path.join(take, "log.jsonl")) as f:
        rows = [json.loads(line) for line in f]
    times = np.array([row["t"] for row in rows])
    segs: list[Segment] = []
    for start, end in KEEP:
        merged = merged_parts(rows, times, start, end)
        for i, (part_start, part_end, name) in enumerate(merged):
            segs.append((part_start, part_end, name, i == 0, i == len(merged) - 1))
    return segs


def merged_parts(rows: list[dict[str, Any]], times: np.ndarray, start: float,
                 end: float) -> list[Part]:
    """A kept range cut where the layout changes; a sliver at the start joins the next part, and brief view
    flashes keep the previous layout."""
    cuts = [start]
    cur = layout_at(rows, times, start)
    for moment in np.arange(start, end, 1 / FPS):
        name = layout_at(rows, times, moment)
        if name != cur:
            cuts.append(round(moment, 4))
            cur = name
    cuts.append(end)
    parts = [(cuts[i], cuts[i + 1], layout_at(rows, times, cuts[i] + 1e-3)) for i in range(len(cuts) - 1)]
    if len(parts) > 1 and parts[0][1] - parts[0][0] < MIN_SEG:
        parts = [(parts[0][0], parts[1][1], parts[1][2])] + parts[2:]
    merged: list[Part] = []
    for part in parts:
        if merged and (part[1] - part[0] < MIN_SEG or part[2] == merged[-1][2]):
            merged[-1] = (merged[-1][0], part[1], merged[-1][2])
        else:
            merged.append(part)
    return merged


def render_segment(i: int, seg: Segment, streams: dict[str, str], take: str, work: str) -> str:
    start, end, name, fade_in, fade_out = seg
    dur = end - start
    places, tags = layout(name)
    tag_png = os.path.join(work, f"tags_{name}.png")
    if not os.path.exists(tag_png):
        tag_overlay(tags, tag_png)
    # every caption showing during this segment - also one that began in the previous segment (a view switch
    # mid-caption used to cut it off after a second); times relative to this segment's start
    showing = [caption for caption in CAPTIONS if caption[0] < end and caption[0] + caption[1] > start]
    caps = [(when - start, seconds, text) for when, seconds, text in showing]
    colour = f"0x{BACKGROUND[0]:02x}{BACKGROUND[1]:02x}{BACKGROUND[2]:02x}"
    inputs = ["-f", "lavfi", "-i", f"color=c={colour}:s={WIDTH}x{HEIGHT}:r={FPS}:d={dur:.3f}"]
    for stream, *_ in places:
        inputs += ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", streams[stream]]
    inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", tag_png]
    for j, (_, _, text) in enumerate(caps):
        png = os.path.join(work, f"cap_{i}_{j}.png")
        text_png([(text, CAPTION_SCALE, CAPTION_COLOUR, CAPTION_Y)], png)
        inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", png]
    inputs += ["-ss", f"{start + AUDIO_LEAD:.3f}", "-t", f"{dur:.3f}", "-i", os.path.join(take, "audio.wav")]
    graph = filter_graph(places, caps, seg)
    out = os.path.join(work, f"seg_{i:03d}.mkv")
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
         "-t", f"{dur:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "16",
         "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", out])
    return out


def filter_graph(places: list[Placement], caps: list[Caption], seg: Segment) -> str:
    """ffmpeg's filter graph for a segment; its inputs are the background, the streams, the tags, the
    captions and the sound, in that order."""
    start, end, _, fade_in, fade_out = seg
    dur = end - start
    steps, last = [], "[0:v]"
    for k, (_, x, y, w, h) in enumerate(places):
        steps.append(f"[{k + 1}:v]scale={w}:{h}:flags=neighbor,setpts=PTS-STARTPTS[s{k}]")
        steps.append(f"{last}[s{k}]overlay={x}:{y}:shortest=1[b{k}]")
        last = f"[b{k}]"
    tag_in = len(places) + 1
    steps.append(f"{last}[{tag_in}:v]overlay=0:0:shortest=1[tg]")
    last = "[tg]"
    for j, (cap_at, cap_seconds, _) in enumerate(caps):
        fades = []
        if cap_at >= 0:  # it starts here: fade in
            fades.append(f"fade=t=in:st={cap_at:.2f}:d=0.3:alpha=1")
        if cap_at + cap_seconds <= dur:  # it ends here: fade out
            fades.append(f"fade=t=out:st={max(cap_at, 0, cap_at + cap_seconds - 0.4):.2f}:d=0.4:alpha=1")
        faded = "".join("," + fade for fade in fades)
        steps.append(f"[{tag_in + 1 + j}:v]format=rgba{faded}[c{j}]")
        steps.append(f"{last}[c{j}]overlay=0:0:shortest=1[cc{j}]")
        last = f"[cc{j}]"
    picture_fades = []
    if fade_in:
        picture_fades.append(f"fade=t=in:st=0:d={DIP}")
    if fade_out:
        picture_fades.append(f"fade=t=out:st={dur - DIP:.3f}:d={DIP}")
    steps.append(f"{last}{','.join(picture_fades) if picture_fades else 'null'},format=yuv420p[v]")
    audio_in = tag_in + 1 + len(caps)
    sound_in, sound_out = (DIP if fade_in else CUT), (DIP if fade_out else CUT)
    sound = ["aresample=48000", "asetpts=PTS-STARTPTS", f"afade=t=in:st=0:d={sound_in}",
             f"afade=t=out:st={dur - sound_out:.3f}:d={sound_out}"]
    steps.append(f"[{audio_in}:a]{','.join(sound)}[a]")
    return ";".join(steps)


def card(lines: list[Line], seconds: float, path: str, work: str,
         audio: tuple[str, float] | None = None) -> str:
    png = os.path.join(work, os.path.basename(path) + ".png")
    text_png(lines, png, background=BACKGROUND)
    if audio is None:
        a_in = ["-f", "lavfi", "-t", f"{seconds}", "-i", "anullsrc=r=48000:cl=stereo"]
    else:
        a_in = ["-ss", f"{audio[1]:.3f}", "-t", f"{seconds}", "-i", audio[0]]
    graph = (f"[0:v]fade=t=in:st=0:d=0.6,fade=t=out:st={seconds - 0.6}:d=0.6,format=yuv420p[v];"
             f"[1:a]aresample=48000,afade=t=in:st=0:d=0.3,afade=t=out:st={seconds - 0.8}:d=0.8[a]")
    picture = ["-loop", "1", "-t", f"{seconds}", "-r", str(FPS), "-i", png]
    encoding = ["-c:v", "libx264", "-preset", "medium", "-crf", "16",
                "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2"]
    run(["ffmpeg", "-v", "error", "-y", *picture, *a_in, "-filter_complex", graph,
         "-map", "[v]", "-map", "[a]", "-t", f"{seconds}", "-r", str(FPS), *encoding, path])
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("take")
    parser.add_argument("-o", "--out")
    args = parser.parse_args()
    take = args.take.rstrip("/")
    load_edit(take)
    work = os.path.join(take, "edit")
    os.makedirs(work, exist_ok=True)
    print("resampling streams to 60 fps on the wall clock...", flush=True)
    streams = cfr_streams(take, work)
    segs = plan(take)
    audio = os.path.join(take, "audio.wav")
    parts = [card(TITLE, 4.0, os.path.join(work, "title.mkv"), work, audio=(audio, 0.0))]
    for i, seg in enumerate(segs):
        print(f"segment {i + 1}/{len(segs)}: {seg[0]:6.1f}-{seg[1]:6.1f}s {seg[2]}", flush=True)
        parts.append(render_segment(i, seg, streams, take, work))
    parts.append(card(END, 6.0, os.path.join(work, "end.mkv"), work))
    lst = os.path.join(work, "parts.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.abspath(part)}'\n" for part in parts)
    out = args.out or os.path.join(take, "adventure_remastered.mp4")
    # video copied as is; the audio is encoded to AAC once, here (no per-segment padding to pile up)
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    print(out)


if __name__ == "__main__":
    main()
