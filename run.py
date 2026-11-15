"""Run the simulation experiments.

    python run.py experiments                 # 500 classes per method and room
    python run.py experiments --runs 20       # quick look
    python run.py experiments --methods one_stack calling --rooms g24
    python run.py sensitivity                 # vary each assumption (60 classes per setting)
    python run.py sensitivity --runs 20       # quicker

experiments: writes outputs/runs.csv (one row per simulated class) and outputs/summary.md.
Seed k gives the same seating, shuffle and speeds in every method
(common random numbers), so methods are compared on identical classes.

sensitivity: one-at-a-time sensitivity check (Saltelli et al., 2008). Each assumed
parameter is set to a low and a high value while everything else stays at its
default, reusing the same seeds. Writes outputs/sensitivity.csv and outputs/sensitivity.md.
"""
import argparse
import copy
import csv
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from quizsim.common import load_params
from quizsim.layout import load_room
from quizsim.methods import METHODS, run


# ---------------------------------------------------------------- experiments

ROOMS = {"room1": "config/rooms/room1_science_east.yaml",
         "g24": "config/rooms/g24_agriculture.yaml"}
FIELDS = ["room", "method", "seed", "t_done", "returned", "unclaimed", "leftovers",
          "teaching_lost_s", "after_class_s", "distraction_min", "student_time_min",
          "exposure_mean", "stood_up", "peak_busy", "timed_out"]

_cache = {}


def _one_class(args):
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


def experiments():
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
        rows = list(ex.map(_one_class, jobs, chunksize=4))
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


# ---------------------------------------------------------------- sensitivity

STACKS = ["one_stack", "two_stacks", "per_table"]
PILES = ["pile_desk"]
ALL = list(METHODS)

# (section, key, label, low, high, methods it affects)
SETTINGS = [
    ("search", "per_sheet_mean", "b, seconds per sheet (0.6)", 0.3, 1.0, STACKS + PILES),
    ("search", "base_time", "a, setup time (3 s)", 1.5, 6.0, STACKS + PILES),
    ("search", "p_miss", "q, chance of missing your sheet (2%)", 0.0, 0.05, STACKS + PILES),
    ("handover", "reach", "reach for a seated hand-over (2.5 m)", 1.7, 3.0, STACKS),
    ("handover", "time", "hand-over time (2 s)", 1.0, 4.0, STACKS + ["calling"]),
    ("walking", "indoor_factor", "walking speed indoors (×0.8)", 0.6, 1.0, ALL),
    ("calling", "p_repeat", "chance a name needs repeating (30%)", 0.0, 0.6, ["calling"]),
    ("calling", "call_time", "time to read a name (2 s)", 1.0, 4.0, ["calling"]),
    ("pile", "max_at_pile", "people at the pile at once (4)", 2, 6, PILES),
    ("pile", "patience_median", "patience before giving up (unlimited)", 120.0, 600.0, PILES),
]

_rooms = {}


def _one_setting(job):
    room_key, method, seed, setting, level, value = job
    P = load_params("config/params.yaml")
    if setting is not None:
        sec, key = SETTINGS[setting][:2]
        P = copy.deepcopy(P)
        P[sec][key] = value
    if room_key not in _rooms:
        _rooms[room_key] = load_room(ROOMS[room_key], P["sim"]["cell"])
    _, m = run(method, _rooms[room_key], P, seed)
    return dict(room=room_key, method=method, seed=seed, setting=-1 if setting is None else setting,
                level=level, t_done=m["t_done"], unclaimed=m["unclaimed"],
                teaching_lost_s=m["teaching_lost_s"], distraction_min=m["distraction_min"],
                timed_out=m["timed_out"])


def sensitivity():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=60)
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args()

    jobs = [(rk, mk, s, None, "default", None) for rk in ROOMS for mk in ALL for s in range(args.runs)]
    for si, (sec, key, label, lo, hi, meths) in enumerate(SETTINGS):
        for level, v in (("low", lo), ("high", hi)):
            jobs += [(rk, mk, s, si, level, v) for rk in ROOMS for mk in meths for s in range(args.runs)]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        rows = list(ex.map(_one_setting, jobs, chunksize=4))
    with open(os.path.join(args.out, "sensitivity.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    def med(rk, mk, si, level, k="t_done"):
        v = [r[k] for r in rows if r["room"] == rk and r["method"] == mk and r["setting"] == si and r["level"] == level]
        return float(np.median(v)) if k == "t_done" else float(np.mean(v))

    out = [f"# Sensitivity check: {args.runs} classes per method, room and setting\n",
           "Median finish time; for the piles also mean students without their quiz. "
           "Each row changes one assumption; everything else stays at its default.\n"]
    for rk in ROOMS:
        out.append(f"\n## {rk}\n")
        out.append("| Assumption | Value | " + " | ".join(METHODS[m][0].split(" · ")[0] for m in ALL)
                   + " | In-class ranking (fastest first) |")
        out.append("|---|---|" + "---|" * len(ALL) + "---|")

        def line(label, val, si, level):
            cells, inclass = [], {}
            for mk in ALL:
                use_si, use_lv = (si, level) if si == -1 or mk in SETTINGS[si][5] else (-1, "default")
                t = med(rk, mk, use_si, use_lv)
                cell = mmss(t)
                if mk in PILES:
                    cell += f" ({med(rk, mk, use_si, use_lv, 'unclaimed'):.0f} left)"
                if mk not in PILES:
                    inclass[mk] = t
                cells.append(cell)
            rank = " < ".join(METHODS[m][0].split(" · ")[0] for m in sorted(inclass, key=inclass.get))
            out.append(f"| {label} | {val} | " + " | ".join(cells) + f" | {rank} |")

        line("**Defaults**", "", -1, "default")
        for si, (sec, key, label, lo, hi, meths) in enumerate(SETTINGS):
            line(label, lo, si, "low")
            line("", hi, si, "high")
    out.append("\nMethods: " + "; ".join(METHODS[m][0] for m in ALL) + ".")
    text = "\n".join(out)
    with open(os.path.join(args.out, "sensitivity.md"), "w") as f:
        f.write(text + "\n")
    print(text)
    print(f"\n{len(rows)} classes in {time.time() - t0:.0f}s; timed out: {sum(r['timed_out'] for r in rows)}")


COMMANDS = {"experiments": experiments, "sensitivity": sensitivity}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit("usage: python run.py {experiments,sensitivity} [options]")
    cmd = sys.argv.pop(1)
    sys.argv[0] = f"run.py {cmd}"
    COMMANDS[cmd]()
