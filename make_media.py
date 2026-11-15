"""Charts, cover image and videos.

    python make_media.py chart                          # all five methods -> outputs/comparison.png
    python make_media.py chart --methods one_stack per_table pile_desk --out outputs/comparison_video.png
    python make_media.py cover                          # cover image -> outputs/cover.png
    python make_media.py videos                         # one video per method -> outputs/videos/
    python make_media.py videos --still one_stack       # preview frames instead
    python make_media.py videos pile_desk one_stack per_table --seconds 20 --hold 3 --out outputs/videos_short
    python make_media.py linkedin                       # cover + clips stitched into one video
"""
import argparse
import csv
import math
import os
import subprocess
import sys
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.patches import Ellipse, Rectangle  # noqa: E402

from quizsim.common import load_params  # noqa: E402
from quizsim.layout import load_room  # noqa: E402
from quizsim.methods import METHODS, run  # noqa: E402
from quizsim.render import BG, INK, INK2, MUTED, render_method, render_still  # noqa: E402


# ----------------------------------------------------------------------------
# chart: comparison chart of the methods
#
# Comparison chart of all methods from outputs/runs.csv -> outputs/comparison.png.
#
# Dot = median finish time over 500 simulated classes; line = 8 in 10 classes
# (10th–90th percentile). Right-hand columns: median teaching time lost and mean
# students left without their quiz.
# ----------------------------------------------------------------------------

CHART_ROOMS = [("room1", "Room E1.17", "#2a78d6"), ("g24", "Room G24", "#eb6834")]
ORDER = [
    ("one_stack", "One stack, passed along"),
    ("two_stacks", "Two stacks, one from each end"),
    ("per_table", "One stack per table"),
    ("calling", "Calling names"),
    ("pile_desk", "Pile on my desk"),
]
AFTER = {"pile_desk"}
GRID = "#e4e2db"
CHAOS = "#e34948"
EMPTY = "#e4e2db"
BAND = "#efede7"
WIN = "#0f7a52"


def mmss(s):
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def chart(path="outputs/runs.csv", out="outputs/comparison.png", only=None):
    order = [o for o in ORDER if only is None or o[0] in only]
    data = defaultdict(lambda: defaultdict(list))
    for r in csv.DictReader(open(path)):
        d = data[(r["room"], r["method"])]
        for k in ("t_done", "teaching_lost_s", "unclaimed", "stood_up", "peak_busy"):
            d[k].append(float(r[k]))
    n_runs = len(data[("room1", "one_stack")]["t_done"])

    fig = plt.figure(figsize=(10.8, 13.5), dpi=100, facecolor=BG)
    fig.text(0.06, 0.955, "How long does it take to return 60 quizzes?", color=INK, fontsize=25,
             fontweight="bold", va="center")

    ax = fig.add_axes([0.33, 0.19, 0.29, 0.66], facecolor=BG)
    ys = np.arange(len(order))[::-1] * 1.0
    # fastest typical class in each room (anything within 10 s of it counts as a tie)
    med = {(rk, mk): np.median(data[(rk, mk)]["t_done"]) for rk, _, _ in CHART_ROOMS for mk, _ in order}
    best = {rk: min(med[(rk, mk)] for mk, _ in order) for rk, _, _ in CHART_ROOMS}
    best_in = {rk: min(med[(rk, mk)] for mk, _ in order if mk not in AFTER) for rk, _, _ in CHART_ROOMS}
    for y, (mk, _) in zip(ys, order):
        for k, (rk, _, col) in enumerate(CHART_ROOMS):
            t = np.array(data[(rk, mk)]["t_done"]) / 60
            yy = y + (0.17 if k == 0 else -0.17)
            hi = np.percentile(t, 90)
            ax.plot([np.percentile(t, 10), hi], [yy, yy], color=col, lw=2,
                    solid_capstyle="round", zorder=2)
            ax.scatter([np.median(t)], [yy], s=90, color=col, edgecolors=BG, linewidths=2, zorder=3)
            if mk in AFTER:
                tag = "  fast, but after class"
            else:
                tag = "  fastest during class" if med[(rk, mk)] == best_in[rk] else ""
            win = bool(tag) and mk not in AFTER
            ax.text(hi + 0.35, yy, mmss(med[(rk, mk)]) + tag,
                    color=WIN if win else INK2, fontsize=11.5, va="center",
                    fontweight="bold" if tag else "normal")
    ax.axhspan(ys[-1] - 0.5, ys[-1] + 0.5, color=BAND, zorder=0)
    ax.set_ylim(ys[-1] - 0.6, ys[0] + 0.6)
    ax.set_xlim(0, 21)
    ax.set_xticks(range(0, 19, 3))
    ax.tick_params(colors=MUTED, labelsize=12, length=0)
    ax.set_yticks([])
    ax.grid(axis="x", color=GRID, lw=0.8, zorder=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_xlabel("minutes until every quiz is back\n(dot and time = typical class, line = 8 in 10 classes)",
                  color=INK2, fontsize=11.5, labelpad=10)

    # method names
    for y, (mk, label) in zip(ys, order):
        yf = ax.transData.transform((0, y))[1] / fig.bbox.height
        fig.text(0.06, yf + 0.008, label, color=INK, fontsize=14, va="center", fontweight="bold")
        fig.text(0.06, yf - 0.018, "after class" if mk in AFTER else "during class", color=MUTED,
                 fontsize=11, va="center")
        lost = np.median(data[("room1", mk)]["teaching_lost_s"]), np.median(data[("g24", mk)]["teaching_lost_s"])
        unc = np.mean(data[("room1", mk)]["unclaimed"] + data[("g24", mk)]["unclaimed"])
        lost_txt = "none" if mk in AFTER else ("all of it" if mk == "calling" else f"{mmss(min(lost))}–{mmss(max(lost))}")
        ups = [np.median(data[(rk, mk)]["stood_up"]) for rk in ("room1", "g24")]
        busy = [np.median(data[(rk, mk)]["peak_busy"]) for rk in ("room1", "g24")]
        rng_txt = lambda v: f"{min(v):.0f}" if min(v) == max(v) else f"{min(v):.0f}–{max(v):.0f}"  # noqa: E731
        fig.text(0.695, yf, lost_txt, color=INK, fontsize=13, va="center")
        # chaos meter: one block per student busy at the same moment (10 = 10 or more)
        n_fill = 10 if mk in AFTER else int(min(10, max(busy)))
        for b in range(10):
            fig.patches.append(Rectangle((0.785 + b * 0.0108, yf + 0.004), 0.0088, 0.016,
                                         transform=fig.transFigure, figure=fig, lw=0,
                                         facecolor=CHAOS if b < n_fill else EMPTY))
        chaos_txt = ("all 50 crowd my desk" if mk in AFTER else
                     f"{rng_txt(busy)} at once · {rng_txt(ups)} get-ups")
        fig.text(0.785, yf - 0.017, chaos_txt, color=INK2, fontsize=9.5, va="center")
        fig.text(0.97, yf, f"{unc:.1f}", color=INK, fontsize=13, va="center", ha="center")
    top = ax.transData.transform((0, ys[0] + 0.6))[1] / fig.bbox.height
    fig.text(0.695, top + 0.012, "teaching\nI lose", color=INK2, fontsize=11, va="bottom", linespacing=1.2)
    fig.text(0.785, top + 0.012, "chaos in the room\n(students busy\nat the same time)", color=INK2, fontsize=11,
             va="bottom", linespacing=1.2)
    fig.text(0.97, top + 0.012, "no\nquiz", color=INK2, fontsize=11, va="bottom",
             ha="center", linespacing=1.2)

    # legend
    lx = 0.33
    for _, name, col in CHART_ROOMS:
        fig.text(lx, top + 0.018, "●", color=col, fontsize=16, va="bottom")
        fig.text(lx + 0.025, top + 0.02, name, color=INK2, fontsize=12.5, va="bottom")
        lx += 0.17

    fig.text(0.06, 0.118, "During class = quizzes go back while I keep teaching.",
             color=INK, fontsize=11.5, va="center")
    fig.savefig(out, facecolor=BG, dpi=100)
    print(out)


def chart_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", nargs="+", default=None, help="only these methods (in the standard order)")
    ap.add_argument("--out", default="outputs/comparison.png")
    a = ap.parse_args()
    chart(out=a.out, only=a.methods)


# ----------------------------------------------------------------------------
# cover: cover image for the LinkedIn video
#
# Cover image for the LinkedIn video: outputs/cover.png (1080 x 1350).
#
# Every number is read from outputs/runs.csv, so the image always matches the
# latest results. Design: one typeface family (Inter / Inter Display), one accent
# colour for the method I chose, text left-aligned on a 72 px margin, and a small
# set of sizes (66 px headline, 96 px key numbers, 36 / 28 / 22 px text).
# ----------------------------------------------------------------------------

for f in fm.findSystemFonts():
    if "Inter" in f:
        fm.fontManager.addfont(f)

W_PX, H_PX = 1080, 1350
PT = 72 / 100                       # points per pixel at dpi 100
P = dict(bg="#FAF8F3", ink="#161616", grey="#6E6B66", rule="#DAD6CE", acc="#1F5FBF")
M = 72 / W_PX                       # left / right margin

ROWS = [("pile_desk", "Pile on my desk"),
        ("per_table", "One stack per table"),
        ("one_stack", "One stack, passed along")]
MINE = "one_stack"


def px(v):
    return v * PT


def half(x):
    return round(x * 2) / 2


def fmt_half(x):
    whole = int(x)
    return f"{whole}½" if x - whole == 0.5 else f"{whole}"


def load(path="outputs/runs.csv"):
    d = defaultdict(lambda: defaultdict(list))
    for r in csv.DictReader(open(path)):
        for k in ("t_done", "teaching_lost_s", "peak_busy"):
            d[(r["room"], r["method"])][k].append(float(r[k]))
    med = lambda rk, mk, k: float(np.median(d[(rk, mk)][k]))  # noqa: E731
    out = {}
    for mk, _ in ROWS:
        t = sorted(half(med(rk, mk, "t_done") / 60) for rk in ("room1", "g24"))
        time = fmt_half(t[0]) if t[0] == t[1] else f"{fmt_half(t[0])}–{fmt_half(t[1])}"
        lost = max(med(rk, mk, "teaching_lost_s") for rk in ("room1", "g24"))
        busy = sorted(med(rk, mk, "peak_busy") for rk in ("room1", "g24"))
        out[mk] = dict(time=time, lost=lost, busy=busy)
    return out


def facts(mk, v):
    if mk == "pile_desk":
        return "After class: everyone\ncrowds my desk"
    if v["lost"] < 10:
        return "I lose under 10 s\nand keep teaching"
    return f"I lose up to {fmt_half(math.ceil(v['lost'] / 30) / 2)} min\nof teaching"


def busy_label(mk, v):
    if mk == "pile_desk":
        return "all 50", 10
    lo, hi = int(v["busy"][0]), int(v["busy"][1])
    return (f"{lo}" if lo == hi else f"{lo}–{hi}"), min(10, hi)


def cover(out="outputs/cover.png"):
    data = load()
    fig = plt.figure(figsize=(W_PX / 100, H_PX / 100), dpi=100, facecolor=P["bg"])
    y_ = lambda p: 1 - p / H_PX  # noqa: E731  (pixels from the top -> figure y)
    fig.text(M, y_(90), "I simulated handing back\nquizzes 5,000 times.", fontfamily="Inter Display",
             fontweight="bold", fontsize=px(66), color=P["ink"], va="top", linespacing=1.05)
    fig.text(M, y_(262), "Three ways to hand back 60 marked quizzes", fontfamily="Inter",
             fontsize=px(30), color=P["grey"], va="top")
    r = fig.canvas.get_renderer()
    top, rowh = 400, 270
    for i, (mk, name) in enumerate(ROWS):
        v, y0 = data[mk], top + i * rowh
        col = P["acc"] if mk == MINE else P["ink"]
        fig.add_artist(plt.Line2D([M, 1 - M], [y_(y0)] * 2, transform=fig.transFigure, color=P["rule"], lw=1.5))
        fig.text(M, y_(y0 + 34), name, fontfamily="Inter", fontweight="bold", fontsize=px(36), color=col, va="top")
        if mk == MINE:
            fig.text(1 - M, y_(y0 + 40), "MY CHOICE", fontfamily="Inter", fontweight="bold", fontsize=px(22),
                     color=P["acc"], va="top", ha="right")
        big = fig.text(M, y_(y0 + 100), v["time"], fontfamily="Inter Display", fontweight="bold",
                       fontsize=px(96), color=col, va="top")
        bw = big.get_window_extent(r).width
        fig.text(M + (bw + 14) / W_PX, y_(y0 + 150), "min", fontfamily="Inter", fontsize=px(34),
                 color=P["grey"], va="top")
        fig.text(0.40, y_(y0 + 112), facts(mk, v), fontfamily="Inter", fontsize=px(28), color=P["ink"],
                 va="top", linespacing=1.35)
        label, n_fill = busy_label(mk, v)
        fig.text(0.73, y_(y0 + 104), "Busy at once", fontfamily="Inter", fontsize=px(22), color=P["grey"], va="top")
        fig.text(0.73, y_(y0 + 134), label, fontfamily="Inter", fontweight="bold", fontsize=px(30), color=col, va="top")
        for k in range(10):
            cx = 0.73 + (k % 5) * 0.034 + 0.012
            cy = y_(y0 + 200 + (k // 5) * 34)
            fig.add_artist(Ellipse((cx, cy), 0.023, 0.023 * W_PX / H_PX, transform=fig.transFigure,
                                   color=col if k < n_fill else P["rule"], lw=0))
    yb = top + 3 * rowh
    fig.add_artist(plt.Line2D([M, 1 - M], [y_(yb)] * 2, transform=fig.transFigure, color=P["rule"], lw=1.5))
    fig.text(M, 44 / H_PX, "Two real lecture rooms · 500 simulated classes per method in each",
             fontfamily="Inter", fontsize=px(24), color=P["grey"], va="bottom")
    fig.savefig(out, facecolor=P["bg"])
    plt.close(fig)
    print(out, data)


# ----------------------------------------------------------------------------
# videos: one video per method, both rooms stacked
#
# One video per method, both rooms stacked.
#
#     python make_media.py videos --still one_stack     # one preview frame (PNG)
#     python make_media.py videos one_stack calling     # chosen methods
#     python make_media.py videos                       # all five
#
# Each room shows a *typical* class: the seed whose finish time is closest to
# the median of the 500-class experiment (outputs/runs.csv). The end card
# quotes the 500-class results.
# ----------------------------------------------------------------------------

ROOMS = {"room1": "config/rooms/room1_science_east.yaml",
         "g24": "config/rooms/g24_agriculture.yaml"}

TEXT = {
    "one_stack": ("One stack, passed along",
                  "I hand the stack to one student and keep teaching.\n"
                  "Each student finds their quiz and passes the rest on."),
    "two_stacks": ("Two stacks, one from each end",
                   "The stack is split in two and starts at both ends of the room.\n"
                   "Each stack has to reach everyone still looking."),
    "per_table": ("One stack per table",
                  "I place a small stack on every occupied table (G24: each half-row).\n"
                  "A stack goes round its table, then on to a new table."),
    "calling": ("Calling names",
                "I read each name and walk the quiz to the student.\n"
                "Deep inside a bench, it is passed along the row."),
    "pile_desk": ("Pile on my desk, after class",
                  "Everyone collects their own quiz on the way out.\n"
                  "Only the four or so people at the desk can search it at once."),
    "pile_door": ("One pile at the door, after class",
                  "The same pile, now beside the door everyone leaves through.\n"
                  "About four people can search the pile at once."),
}


def load_runs():
    rows = []
    for path in ("outputs/runs.csv",):
        if os.path.exists(path):
            rows += list(csv.DictReader(open(path)))
    out = {}
    for r in rows:                       # later files (recalibrated piles) override earlier ones
        out[(r["room"], r["method"], int(r["seed"]))] = r
    return list(out.values())


def stats(rows, room, method):
    r = [x for x in rows if x["room"] == room and x["method"] == method]
    t = np.array([float(x["t_done"]) for x in r])
    return dict(seeds=[int(x["seed"]) for x in r], t=t,
                median=np.median(t), p10=np.percentile(t, 10), p90=np.percentile(t, 90),
                unclaimed=np.mean([float(x["unclaimed"]) for x in r]),
                lost=np.median([float(x["teaching_lost_s"]) for x in r]), n=len(r))


def minutes(s):
    return f"{s / 60:.0f}"


def end_card(method, st):
    a, b = st["room1"], st["g24"]
    lines = [f"Across {a['n']} simulated classes per room",
             f"E1.17: {minutes(a['median'])} min (8 in 10 classes: {minutes(a['p10'])}–{minutes(a['p90'])})"
             f"   ·   G24: {minutes(b['median'])} min ({minutes(b['p10'])}–{minutes(b['p90'])})"]
    un = (a["unclaimed"] + b["unclaimed"]) / 2
    got = "Every student got their quiz" if un < 0.05 else \
        ("About 1 student per class ended without their quiz" if round(un, 1) == 1.0 else
         f"About {un:.1f} students per class ended without their quiz")
    if method.startswith("pile"):
        tail = "all of it after class"
    elif method == "calling":
        tail = "all of it taken from my teaching"
    else:
        tail = f"I lose about {max(1, round(min(a['lost'], b['lost'])))}–{max(1, round(max(a['lost'], b['lost'])))} s of teaching"
    lines.append(f"{got}  ·  {tail}")
    return "\n".join(lines)


def videos():
    ap = argparse.ArgumentParser()
    ap.add_argument("methods", nargs="*", default=list(METHODS))
    ap.add_argument("--still", action="store_true", help="save one preview frame per method instead")
    ap.add_argument("--still-at", type=float, default=0.45, help="fraction of the run for the preview")
    ap.add_argument("--out", default="outputs/videos")
    ap.add_argument("--seconds", type=float, default=35, help="target length of the animated part")
    ap.add_argument("--hold", type=float, default=5, help="seconds to hold the end card")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    P = load_params("config/params.yaml")
    rows = load_runs()
    rooms = {k: load_room(v, P["sim"]["cell"]) for k, v in ROOMS.items()}

    for method in args.methods:
        st = {rk: stats(rows, rk, method) for rk in ROOMS}
        sims, ms = [], []
        for rk in ROOMS:
            s = st[rk]
            seed = s["seeds"][int(np.argmin(np.abs(s["t"] - s["median"])))]   # typical class
            sim, m = run(method, rooms[rk], P, seed, record=True)
            sims.append(sim)
            ms.append(m)
        title, sub = TEXT[method]
        end = end_card(method, st)
        if args.still:
            t = max(s["t"][-1] for s in sims) * args.still_at
            p = render_still(list(rooms.values()), sims, ms, method, title, sub, end, t,
                             os.path.join(args.out, f"{method}_preview.png"))
            p2 = render_still(list(rooms.values()), sims, ms, method, title, sub, end, 1e9,
                              os.path.join(args.out, f"{method}_end.png"))
            print(p, p2)
        else:
            out = os.path.join(args.out, f"{method}.mp4")
            info = render_method(list(rooms.values()), sims, ms, method, title, sub, end, out,
                                 target_seconds=args.seconds, hold_seconds=args.hold,
                                 dt=P["sim"]["dt"])
            print(out, info)


# ----------------------------------------------------------------------------
# linkedin: stitch the cover and chosen clips into one video
#
# Stitch the chart and chosen method videos into one LinkedIn video.
#
#     python make_media.py linkedin                               # default order below
#     python make_media.py linkedin --clips pile_desk one_stack   # choose clips
#
# Layout: chart (intro) -> each method clip -> chart again (outro).
# All parts are 1080 x 1350 at 30 fps; short fades join them.
# ----------------------------------------------------------------------------

CLIPS = ["pile_desk", "per_table", "one_stack"]   # same order as the cover: old way -> fastest -> my choice


def linkedin():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", nargs="+", default=CLIPS)
    ap.add_argument("--chart", default="outputs/cover.png")
    ap.add_argument("--videos", default="outputs/videos_short")
    ap.add_argument("--intro", type=float, default=6.0)
    ap.add_argument("--outro", type=float, default=3.0)
    ap.add_argument("--out", default="outputs/linkedin_quiz_return.mp4")
    a = ap.parse_args()

    inputs, filters, labels = [], [], []
    fade = 0.3

    def still(sec, k):
        inputs.extend(["-loop", "1", "-framerate", "30", "-t", f"{sec}", "-i", a.chart])
        filters.append(f"[{k}:v]scale=1080:1350,fps=30,format=yuv420p,setsar=1,"
                       f"fade=t=in:st=0:d={fade},fade=t=out:st={sec - fade}:d={fade}[v{k}]")

    k = 0
    still(a.intro, k)
    labels.append(f"[v{k}]")
    for name in a.clips:
        k += 1
        path = os.path.join(a.videos, f"{name}.mp4")
        dur = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).strip())
        inputs.extend(["-i", path])
        filters.append(f"[{k}:v]scale=1080:1350,fps=30,format=yuv420p,setsar=1,"
                       f"fade=t=in:st=0:d={fade},fade=t=out:st={dur - fade}:d={fade}[v{k}]")
        labels.append(f"[v{k}]")
    k += 1
    still(a.outro, k)
    labels.append(f"[v{k}]")
    filters.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[out]")

    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters),
           "-map", "[out]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out]
    subprocess.run(cmd, check=True)
    dur = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", a.out]).strip().decode()
    print(a.out, f"{float(dur):.1f} s")


COMMANDS = {"chart": chart_cli, "cover": cover, "videos": videos, "linkedin": linkedin}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit("usage: python make_media.py {chart,cover,videos,linkedin} [options]")
    cmd = sys.argv.pop(1)
    sys.argv[0] = f"make_media.py {cmd}"
    COMMANDS[cmd]()
