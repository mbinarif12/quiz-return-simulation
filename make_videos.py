"""One video per method, both rooms stacked.

    python make_videos.py --still one_stack     # one preview frame (PNG)
    python make_videos.py one_stack calling     # chosen methods
    python make_videos.py                       # all six

Each room shows a *typical* class: the seed whose finish time is closest to
the median of the 500-class experiment (outputs/runs.csv). The end card
quotes the 500-class results.
"""
import argparse
import csv
import os

import numpy as np

from quizsim.common import load_params
from quizsim.layout import load_room
from quizsim.methods import METHODS, run
from quizsim.render import render_method, render_still

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


def main():
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


if __name__ == "__main__":
    main()
