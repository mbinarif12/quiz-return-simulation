"""Run every method in every room many times and summarise.

    python run_experiments.py                   # 500 runs per method and room
    python run_experiments.py --runs 20         # quick look
    python run_experiments.py --methods one_stack calling --rooms g24

Writes outputs/runs.csv (one row per simulated class) and outputs/summary.md.
Seed k gives the same seating, shuffle and speeds in every method
(common random numbers), so methods are compared on identical classes.
"""
import argparse
import csv
import os
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from quizsim.common import load_params
from quizsim.layout import load_room
from quizsim.methods import METHODS, run

ROOMS = {"room1": "config/rooms/room1_science_east.yaml",
         "g24": "config/rooms/g24_agriculture.yaml"}
FIELDS = ["room", "method", "seed", "t_done", "returned", "unclaimed", "leftovers",
          "teaching_lost_s", "after_class_s", "distraction_min", "student_time_min",
          "exposure_mean", "stood_up", "peak_busy", "timed_out"]

_cache = {}


def _one(args):
    room_key, method, seed, params_path = args
    if room_key not in _cache:
        P = load_params(params_path)
        _cache[room_key] = (load_room(ROOMS[room_key], P["sim"]["cell"]), P)
    room, P = _cache[room_key]
    _, m = run(method, room, P, seed)
    m["room"] = room_key
    return {k: m[k] for k in FIELDS}


def mmss(s):
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def summarise(rows, rooms, methods):
    lines = []
    for rk in rooms:
        lines.append(f"\n### {rk}\n")
        lines.append("| Method | Finish (median) | 80% of classes | Unclaimed | Teaching lost | "
                     "Distraction (student-min) | Students getting up | Most busy at once | Names seen per student |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for mk in methods:
            r = [x for x in rows if x["room"] == rk and x["method"] == mk]
            if not r:
                continue
            col = lambda k: np.array([float(x[k]) for x in r])  # noqa: E731
            t = col("t_done")
            lines.append(
                f"| {METHODS[mk][0]} | {mmss(np.median(t))} | {mmss(np.percentile(t, 10))}–{mmss(np.percentile(t, 90))} "
                f"| {np.mean(col('unclaimed')):.1f} | {mmss(np.median(col('teaching_lost_s')))} "
                f"| {np.median(col('distraction_min')):.0f} | {np.median(col('stood_up')):.0f} "
                f"| {np.median(col('peak_busy')):.0f} | {np.median(col('exposure_mean')):.0f} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=500)
    ap.add_argument("--methods", nargs="+", default=list(METHODS))
    ap.add_argument("--rooms", nargs="+", default=list(ROOMS))
    ap.add_argument("--params", default="config/params.yaml")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    jobs = [(rk, mk, s, args.params) for rk in args.rooms for mk in args.methods for s in range(args.runs)]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        rows = list(ex.map(_one, jobs, chunksize=4))
    with open(os.path.join(args.out, "runs.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    text = (f"# Results: {args.runs} simulated classes per method and room\n\n"
            "Unclaimed = mean present students without their quiz. Finish for 5a/5b is after class. "
            "Names seen = other students' sheets each student looks at (median).\n" +
            summarise(rows, args.rooms, args.methods))
    with open(os.path.join(args.out, "summary.md"), "w") as f:
        f.write(text + "\n")
    print(text)
    print(f"\n{len(rows)} classes in {time.time() - t0:.0f}s; timed out: {sum(r['timed_out'] for r in rows)}")


if __name__ == "__main__":
    main()
