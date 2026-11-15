"""Cover image for the LinkedIn video: outputs/cover.png (1080 x 1350).

Every number is read from outputs/runs.csv, so the image always matches the
latest results. Design: one typeface family (Inter / Inter Display), one accent
colour for the method I chose, text left-aligned on a 72 px margin, and a small
set of sizes (66 px headline, 96 px key numbers, 36 / 28 / 22 px text).
"""
import csv
import math
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.patches import Ellipse  # noqa: E402

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


def main(out="outputs/cover.png"):
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


if __name__ == "__main__":
    main()
