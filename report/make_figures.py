"""Figures for the technical report (report/fig/)."""
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from quizsim.layout import load_room  # noqa: E402
from quizsim.render import BG, INK, INK2, MUTED, draw_room  # noqa: E402

OUT = "report/fig"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": "#b9b7af", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2})

# 1. rooms with passing route
fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), facecolor="white")
for ax, f, name in zip(axes, ["room1_science_east", "g24_agriculture"], ["E1.17", "G24"]):
    r = load_room(f"config/rooms/{f}.yaml")
    draw_room(ax, r)
    order = sorted(range(len(r.seats)), key=lambda i: r.seat_rank[i])
    xy = np.array([r.centre(r.seats[i]) for i in order])
    ax.plot(xy[:, 0], xy[:, 1], color="#2a78d6", lw=1.1, alpha=0.8, zorder=3)
    ax.scatter(*xy[0], s=60, color="#1baf7a", zorder=4)
    ax.scatter(*xy[-1], s=60, color="#e34948", zorder=4)
    ax.scatter(*r.centre(r.teaching_cell), marker="*", s=160, color="#6250d6", zorder=4)
    ax.set_title(f"{name}: {r.width:g} m × {r.depth:g} m, {len(r.seats)} seats", color=INK, fontsize=11)
fig.text(0.5, 0.02, "Blue line = passing route (green = start, red = end). Star = lecturer's teaching spot. "
         "Front of the room is at the bottom.", ha="center", color=INK2, fontsize=9.5)
fig.tight_layout(rect=(0, 0.05, 1, 1))
fig.savefig(f"{OUT}/rooms.pdf")

# 2. ECDF of finish times
rows = list(csv.DictReader(open("outputs/runs.csv")))
d = defaultdict(list)
for r in rows:
    d[(r["room"], r["method"])].append(float(r["t_done"]) / 60)
M = [("one_stack", "1 One stack", "#2a78d6"), ("two_stacks", "2 Two stacks", "#eb6834"),
     ("per_table", "3 Stack per table", "#1baf7a"), ("calling", "4 Calling names", "#6250d6"),
     ("pile_desk", "5 Pile on desk (after class)", "#e34948")]
fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True, facecolor="white")
for ax, (rk, name) in zip(axes, [("room1", "E1.17"), ("g24", "G24")]):
    for mk, lab, col in M:
        x = np.sort(d[(rk, mk)])
        ax.step(x, np.arange(1, len(x) + 1) / len(x), where="post", color=col, lw=1.8, label=lab)
    ax.set_title(name, color=INK)
    ax.set_xlabel("finish time (minutes)")
    ax.grid(color="#ecebe6")
    ax.set_xlim(3, 24)
axes[0].set_ylabel("share of the 500 classes finished")
axes[1].legend(frameon=False, fontsize=9, loc="lower right")
fig.tight_layout()
fig.savefig(f"{OUT}/ecdf.pdf")

# 3. position distribution check (one stack of 60)
rng = np.random.default_rng(1)
pos = np.array([list(rng.permutation(60)).index(0) + 1 for _ in range(200_000)])
fig, ax = plt.subplots(figsize=(7, 2.6), facecolor="white")
ax.bar(np.arange(1, 61), np.bincount(pos, minlength=61)[1:] / len(pos), color="#2a78d6", width=0.8)
ax.axhline(1 / 60, color="#e34948", lw=1.2, label="theory: 1/60")
ax.set_xlabel("position of your sheet in a shuffled stack of 60")
ax.set_ylabel("share of 200,000 shuffles")
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(f"{OUT}/position.pdf")
print("ok")
