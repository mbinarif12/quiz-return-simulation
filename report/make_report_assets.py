"""Figures and the sensitivity table for the two LaTeX reports.

    python report/make_report_assets.py      # run from the project folder

figures():   report/fig/rooms.pdf, ecdf.pdf, position.pdf (from outputs/runs.csv)
sens_table(): report/sens_table.tex (from outputs/sensitivity.csv)
"""
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
from run import SETTINGS  # noqa: E402


def figures():
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


def sens_table():
    rows = list(csv.DictReader(open("outputs/sensitivity.csv")))
    d = defaultdict(list)
    for r in rows:
        d[(r["room"], r["method"], int(r["setting"]), r["level"])].append(float(r["t_done"]))
    M = ["one_stack", "two_stacks", "per_table", "calling", "pile_desk"]
    runs = len(d[("room1", "one_stack", -1, "default")])
    def med(rk, mk, si, lv):
        k = (rk, mk, si, lv)
        if k not in d:
            k = (rk, mk, -1, "default")
        return np.median(d[k])
    def mm(s):
        s = int(round(s)); return f"{s//60}:{s%60:02d}"
    out = [r"Each assumed parameter was set to a low and a high value, one at a time, with everything else at its default (one-at-a-time design \cite{saltelli2008}).",
           f"Each setting uses the same {runs} seeds (common random numbers). Entries are median finish times (mm:ss); the last column gives the in-class ranking (methods 1--4, fastest first). Method 5 is after class.",
           "", r"{\small\setlength{\tabcolsep}{4pt}"]
    changes = 0
    always3 = always21 = only4 = True
    for rk, name in [("room1", "E1.17"), ("g24", "G24")]:
        out += [r"\begin{table}[htbp]\centering\footnotesize", r"\begin{tabular}{lrrrrrrl}", r"\toprule",
                r"Assumption (default) & Value & 1 & 2 & 3 & 4 & 5 & In-class ranking \\", r"\midrule"]
        base_rank = None
        lines = [("\\textbf{Defaults}", "", -1, "default")]
        for si, (sec, key, label, lo, hi, meths) in enumerate(SETTINGS):
            lines += [(label.replace("%", r"\%").replace("×", r"$\times$"), lo, si, "low"), ("", hi, si, "high")]
        for label, val, si, lv in lines:
            t = {mk: med(rk, mk, si, lv) for mk in M}
            rank = "".join(str(M.index(m) + 1) for m in sorted(M[:4], key=t.get))
            if base_rank is None:
                base_rank = rank
            flag = "" if rank == base_rank else r"\,$\ast$"
            changes += rank != base_rank
            always3 &= rank[0] == "3"
            always21 &= rank.index("2") < rank.index("1")
            if rank != base_rank:
                only4 &= rank.replace("4", "") == base_rank.replace("4", "")
            out.append(f"{label} & {val} & " + " & ".join(mm(t[m]) for m in M) + f" & {'<'.join(rank)}{flag} \\\\")
        out += [r"\bottomrule", r"\end{tabular}",
                f"\\caption{{Sensitivity, room {name}. $\\ast$ = in-class ranking differs from the default ({'<'.join(base_rank)}).}}",
                r"\end{table}"]
    out.append("}")
    n_set = 2 * len(SETTINGS) * 2
    txt = (f"\n\\paragraph{{Summary.}} Across {n_set} settings (both rooms), the in-class ranking changed in {changes}. "
           + ("In every setting, one stack per table (3) was the fastest in-class method" if always3 else "Method 3 was not always fastest")
           + (", and two stacks (2) beat one stack (1)" if always21 else "")
           + (". Every change in ranking involved only the position of calling names (4), which competes closely with one stack in G24 (14:20 vs 14:04 at the defaults) and with two stacks when search is slow. "
              if only4 else ". ")
           + "Search speed $b$ has by far the largest effect on the stack methods (one stack: about 9--20 minutes over $b=0.3$--$1.0$\\,s), which is why measuring it is the first priority.")
    out.append(txt)
    open("report/sens_table.tex", "w").write("\n".join(out) + "\n")
    print("changes", changes)


if __name__ == "__main__":
    figures()
    sens_table()
