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

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root, when run as a script
from shared import hud as HUD
from app import recorder as REC

W, H, FPS = 1920, 1080, 60
BG = (11, 11, 20)
KEY = (1, 2, 3)  # transparent colour for overlay PNGs
STREAM_SIZE = {**REC.STREAMS, "ram": REC.RAM_SIZE}  # + the take's other looks (meta.json)
NAMES = {"nes": "NES REMASTER", "snes": "SNES REMASTER",
         "16bit": "16-BIT REMASTER", "forever": "16-BIT REMASTER"}  # the SNES look's old keys, in older takes

# the edit decision list: filled from <take>/edit.json by load_edit()
KEEP, FORCE, CAPTIONS, GRID16 = [], [], [], "16bit"  # takes before the grid16 log entry
TITLE = [("ADVENTURE", 6, (236, 174, 212), 330), ("ATARI 2600 - 1980 - WARREN ROBINETT", 3, (232, 232, 240), 470),
         ("REMASTERED", 3, (232, 200, 72), 540)]
END = [("ADVENTURE BY WARREN ROBINETT, ATARI 1980", 3, (232, 232, 240), 380),
       ("A FAN PROJECT - NOT FOR SALE", 2, (236, 174, 212), 560)]


def measure_audio_lead(take):
    """How late the take's audio is: for every sound the log saw start, find its onset in audio.wav (the
    2600's effects are far louder than the music) and take the median offset. None if too few found."""
    import wave
    with wave.open(os.path.join(take, "audio.wav")) as w:
        rate = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2).astype(np.float32).mean(axis=1)
    hop = rate // 200  # 5 ms envelope
    env = np.sqrt(np.convolve(a ** 2, np.ones(hop) / hop, mode="same"))[::hop]
    offsets = []
    with open(os.path.join(take, "log.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            if any(e.startswith("SOUND") for e in r.get("events", [])):
                lo, hi = int((r["t"] - 0.3) * 200), int((r["t"] + 1.0) * 200)
                seg = env[lo:hi]
                base = np.median(env[max(0, lo - 200):lo]) if lo > 0 else 0
                hit = np.nonzero(seg > max(base * 2.2, 6000))[0]
                if lo >= 0 and hit.size:
                    offsets.append((lo + hit[0]) / 200 - r["t"])
    return float(np.clip(np.median(offsets), 0, 0.6)) if len(offsets) >= 3 else None


def load_edit(take):
    global KEEP, FORCE, CAPTIONS, GRID16, TITLE, END, AUDIO_LEAD
    with open(os.path.join(take, "edit.json")) as f:
        e = json.load(f)
    with open(os.path.join(take, "meta.json")) as f:
        STREAM_SIZE.update({k: tuple(v) for k, v in json.load(f)["streams"].items()})
    KEEP = [tuple(r) for r in e["keep"]]
    FORCE = [tuple(r) for r in e.get("force", [])]
    CAPTIONS = [tuple(c) for c in e.get("captions", [])]
    GRID16 = e.get("grid16", GRID16)
    TITLE = [(t, s, tuple(c), y) for t, s, c, y in e.get("title", TITLE)]
    END = [(t, s, tuple(c), y) for t, s, c, y in e.get("end", END)]
    NAMES.update(e.get("names", {}))
    lead = e.get("audio_lead", measure_audio_lead(take))
    if lead is not None:
        AUDIO_LEAD = lead
    print(f"audio lead {AUDIO_LEAD:.3f} s", flush=True)
AUDIO_LEAD = 0.15  # sounds come ~0.15-0.35 s after the picture (the game's audio buffer); measured per take
MIN_SEG = 0.6  # view flashes shorter than this (cycling V past a view) keep the previous layout


def run(cmd, timeout=120, tries=4):
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


def text_png(lines, path, size=(W, H), bg=None):
    """lines: (text, scale, rgb, y). bg None = transparent overlay."""
    img = np.zeros((size[1], size[0], 3), np.uint8)
    img[:] = bg if bg is not None else KEY
    for text, scale, rgb, y in lines:
        x = (size[0] - HUD.text_width(text, scale)) // 2
        HUD.draw_text(img, text, x, y, rgb, scale=scale, shadow=(0, 0, 0))
    rgba = np.dstack([img, np.where((img == KEY).all(axis=2), 0, 255).astype(np.uint8)]) if bg is None else img
    Image.fromarray(rgba).save(path)


def tag_overlay(tags, path):
    """Small pane labels: (text, x, y) with a dark box."""
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = KEY
    for text, x, y in tags:
        w = HUD.text_width(text, 2)
        img[y - 6:y + 20, x - 8:x + w + 6] = (0, 0, 0)
        HUD.draw_text(img, text, x, y, (232, 232, 240), scale=2, shadow=None)
    rgba = np.dstack([img, np.where((img == KEY).all(axis=2), 0, 230).astype(np.uint8)])
    Image.fromarray(rgba).save(path)


def layout(name):
    """name: both_<look> / solo_<look> / 2600 / grid_<look> / finale_<look>
    -> (placements [(stream, x, y, w, h)], tags [(text, x, y)])."""
    kind, _, rem = name.partition("_")
    label = NAMES.get(rem, rem.upper())
    if name.startswith("both"):
        return [(rem, 64, 60, 1024, 960), ("a2600", 1176, 312, 640, 456)], \
               [(label, 64, 24), ("ATARI 2600 - 1980", 1176, 276)]
    if kind == "solo":
        return [(rem, 448, 60, 1024, 960)], [(label, 448, 24)]
    if name == "2600":
        return [("a2600", 320, 70, 1280, 912)], [("ATARI 2600 - 1980", 320, 34)]
    if kind == "grid":  # as in play.py: remasters left, the original over its RAM right
        return [("nes", 448, 60, 512, 480), (rem, 448, 540, 512, 480), ("a2600", 960, 117, 512, 365),
                ("ram", 960, 540, 512, 480)], \
               [("NES REMASTER", 448, 24), ("ATARI 2600 - 1980", 960, 24),  # bottom row: side margins (the
                (label, 448 - HUD.text_width(label, 2) - 24, 548),          # captions own the bottom)
                ("INTERNALS", 1472 + 24, 548)]
    if kind == "finale":
        return [("nes", 160, 170, 768, 720), (rem, 992, 170, 768, 720)], \
               [("NES REMASTER", 160, 134), (label, 992, 134)]
    raise ValueError(name)


def cfr_streams(take, work):
    """Each stream -> constant 60 fps on the wall clock (repeat/skip frames by log 't')."""
    with open(os.path.join(take, "log.jsonl")) as f:
        t = np.array([json.loads(line)["t"] for line in f])
    n_out = int(t[-1] * FPS) + 1
    src_for = np.searchsorted(t, np.arange(n_out) / FPS, side="right") - 1
    src_for = np.clip(src_for, 0, len(t) - 1)
    if not os.path.exists(os.path.join(take, "ram.mp4")):
        REC.render_ram_video(take)
    out = {}
    for name, (w, h) in STREAM_SIZE.items():
        dst = os.path.join(work, f"{name}_cfr.mp4")
        out[name] = dst
        if os.path.exists(dst):
            continue
        dec = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", os.path.join(take, f"{name}.mp4"), "-f", "rawvideo",
                                "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                                "-r", str(FPS), "-i", "-", "-c:v", "libx264rgb", "-preset", "ultrafast", "-crf",
                                "0" if name != "ram" else "12", dst], stdin=subprocess.PIPE)
        frame_bytes, cur, cur_i = w * h * 3, None, -1
        for want in src_for:
            while cur_i < want:
                buf = dec.stdout.read(frame_bytes)
                if len(buf) < frame_bytes:
                    break
                cur, cur_i = buf, cur_i + 1
            enc.stdin.write(cur)
        enc.stdin.close()
        enc.wait()
        dec.stdout.close()
        dec.wait()
    return out


def plan(take):
    """KEEP ranges -> segments [(t0, t1, layout, fade_in, fade_out)] following the logged view/version."""
    with open(os.path.join(take, "log.jsonl")) as f:
        rows = [json.loads(line) for line in f]
    t = np.array([r["t"] for r in rows])

    def layout_at(ts):
        for a, b, name in FORCE:
            if a <= ts < b:
                return name
        r = rows[max(0, np.searchsorted(t, ts, side="right") - 1)]
        view, look = r["view"], r["look"]
        return {"both": f"both_{look}", "nes": f"solo_{look}", "look": f"solo_{look}", "2600": "2600",
                "grid": f"grid_{r.get('grid16', GRID16)}"}[view]

    segs = []
    for k, (a, b) in enumerate(KEEP):
        cuts = [a]
        cur = layout_at(a)
        for ts in np.arange(a, b, 1 / FPS):
            name = layout_at(ts)
            if name != cur:
                cuts.append(round(ts, 4))
                cur = name
        cuts.append(b)
        parts = [(cuts[i], cuts[i + 1], layout_at(cuts[i] + 1e-3)) for i in range(len(cuts) - 1)]
        if len(parts) > 1 and parts[0][1] - parts[0][0] < MIN_SEG:  # a sliver at the start joins the next part
            parts = [(parts[0][0], parts[1][1], parts[1][2])] + parts[2:]
        merged = []
        for p in parts:  # brief view flashes keep the previous layout
            if merged and (p[1] - p[0] < MIN_SEG or p[2] == merged[-1][2]):
                merged[-1] = (merged[-1][0], p[1], merged[-1][2])
            else:
                merged.append(p)
        for i, (s0, s1, name) in enumerate(merged):
            segs.append((s0, s1, name, i == 0, i == len(merged) - 1))
    return segs


def render_segment(i, seg, streams, take, work):
    t0, t1, name, fade_in, fade_out = seg
    dur = t1 - t0
    places, tags = layout(name)
    tag_png = os.path.join(work, f"tags_{name}.png")
    if not os.path.exists(tag_png):
        tag_overlay(tags, tag_png)
    # every caption showing during this segment - also one that began in the previous segment (a view switch
    # mid-caption used to cut it off after a second); times relative to this segment's start
    caps = [(ct - t0, cd, text) for ct, cd, text in CAPTIONS if ct < t1 and ct + cd > t0]
    inputs = ["-f", "lavfi", "-i", f"color=c=0x{BG[0]:02x}{BG[1]:02x}{BG[2]:02x}:s={W}x{H}:r={FPS}:d={dur:.3f}"]
    for s, *_ in places:
        inputs += ["-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", streams[s]]
    inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", tag_png]
    for j, (_, _, text) in enumerate(caps):
        p = os.path.join(work, f"cap_{i}_{j}.png")
        text_png([(text, 3, (255, 236, 140), 1032)], p)
        inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", p]
    inputs += ["-ss", f"{t0 + AUDIO_LEAD:.3f}", "-t", f"{dur:.3f}", "-i", os.path.join(take, "audio.wav")]
    f, last = [], "[0:v]"
    for k, (s, x, y, w, h) in enumerate(places):
        f.append(f"[{k + 1}:v]scale={w}:{h}:flags=neighbor,setpts=PTS-STARTPTS[s{k}]")
        f.append(f"{last}[s{k}]overlay={x}:{y}:shortest=1[b{k}]")
        last = f"[b{k}]"
    tag_in = len(places) + 1
    f.append(f"{last}[{tag_in}:v]overlay=0:0:shortest=1[tg]")
    last = "[tg]"
    for j, (ct, cd, _) in enumerate(caps):
        ci = tag_in + 1 + j
        fades = []
        if ct >= 0:  # it starts here: fade in
            fades.append(f"fade=t=in:st={ct:.2f}:d=0.3:alpha=1")
        if ct + cd <= dur:  # it ends here: fade out
            fades.append(f"fade=t=out:st={max(ct, 0, ct + cd - 0.4):.2f}:d=0.4:alpha=1")
        f.append(f"[{ci}:v]format=rgba{''.join(',' + x for x in fades)}[c{j}]")
        f.append(f"{last}[c{j}]overlay=0:0:shortest=1[cc{j}]")
        last = f"[cc{j}]"
    vf = []
    if fade_in:
        vf.append("fade=t=in:st=0:d=0.25")
    if fade_out:
        vf.append(f"fade=t=out:st={dur - 0.25:.3f}:d=0.25")
    f.append(f"{last}{','.join(vf) if vf else 'null'},format=yuv420p[v]")
    audio_in = tag_in + 1 + len(caps)
    af = [f"aresample=48000", "asetpts=PTS-STARTPTS"]
    af.append(f"afade=t=in:st=0:d={0.25 if fade_in else 0.03}")
    af.append(f"afade=t=out:st={dur - (0.25 if fade_out else 0.03):.3f}:d={0.25 if fade_out else 0.03}")
    f.append(f"[{audio_in}:a]{','.join(af)}[a]")
    out = os.path.join(work, f"seg_{i:03d}.mkv")
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(f), "-map", "[v]", "-map", "[a]",
         "-t", f"{dur:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "16",
         "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", out])
    return out


def card(lines, seconds, path, work, audio=None):
    png = os.path.join(work, os.path.basename(path) + ".png")
    text_png(lines, png, bg=BG)
    a_in = ["-f", "lavfi", "-t", f"{seconds}", "-i", "anullsrc=r=48000:cl=stereo"] if audio is None else \
        ["-ss", f"{audio[1]:.3f}", "-t", f"{seconds}", "-i", audio[0]]
    run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-t", f"{seconds}", "-r", str(FPS), "-i", png, *a_in,
         "-filter_complex", f"[0:v]fade=t=in:st=0:d=0.6,fade=t=out:st={seconds - 0.6}:d=0.6,format=yuv420p[v];"
                            f"[1:a]aresample=48000,afade=t=in:st=0:d=0.3,afade=t=out:st={seconds - 0.8}:d=0.8[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{seconds}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium",
         "-crf", "16", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", path])
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("take")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()
    take = args.take.rstrip("/")
    load_edit(take)
    work = os.path.join(take, "edit")
    os.makedirs(work, exist_ok=True)
    print("resampling streams to 60 fps on the wall clock...", flush=True)
    streams = cfr_streams(take, work)
    segs = plan(take)
    parts = [card(TITLE, 4.0, os.path.join(work, "title.mkv"), work, audio=(os.path.join(take, "audio.wav"), 0.0))]
    for i, seg in enumerate(segs):
        print(f"segment {i + 1}/{len(segs)}: {seg[0]:6.1f}-{seg[1]:6.1f}s {seg[2]}", flush=True)
        parts.append(render_segment(i, seg, streams, take, work))
    parts.append(card(END, 6.0, os.path.join(work, "end.mkv"), work))
    lst = os.path.join(work, "parts.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in parts)
    out = args.out or os.path.join(take, "adventure_remastered.mp4")
    # video copied as is; the audio is encoded to AAC once, here (no per-segment padding to pile up)
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    print(out)


if __name__ == "__main__":
    main()
