"""Comparison chart of all methods from outputs/runs.csv -> outputs/comparison.png.

Dot = median finish time over 500 simulated classes; line = 8 in 10 classes
(10th–90th percentile). Right-hand columns: median teaching time lost and mean
students left without their quiz.
"""
import csv
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from quizsim.render import BG, INK, INK2, MUTED  # noqa: E402

ROOMS = [("room1", "Room E1.17", "#2a78d6"), ("g24", "Room G24", "#eb6834")]
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


def main(path="outputs/runs.csv", out="outputs/comparison.png", only=None):
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
    med = {(rk, mk): np.median(data[(rk, mk)]["t_done"]) for rk, _, _ in ROOMS for mk, _ in order}
    best = {rk: min(med[(rk, mk)] for mk, _ in order) for rk, _, _ in ROOMS}
    best_in = {rk: min(med[(rk, mk)] for mk, _ in order if mk not in AFTER) for rk, _, _ in ROOMS}
    for y, (mk, _) in zip(ys, order):
        for k, (rk, _, col) in enumerate(ROOMS):
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
    for _, name, col in ROOMS:
        fig.text(lx, top + 0.018, "●", color=col, fontsize=16, va="bottom")
        fig.text(lx + 0.025, top + 0.02, name, color=INK2, fontsize=12.5, va="bottom")
        lx += 0.17

    fig.text(0.06, 0.118, "During class = quizzes go back while I keep teaching.",
             color=INK, fontsize=11.5, va="center")
    fig.savefig(out, facecolor=BG, dpi=100)
    print(out)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", nargs="+", default=None, help="only these methods (in the standard order)")
    ap.add_argument("--out", default="outputs/comparison.png")
    a = ap.parse_args()
    main(out=a.out, only=a.methods)
