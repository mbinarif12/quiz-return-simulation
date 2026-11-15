"""One-at-a-time sensitivity check (Saltelli et al., 2008).

Each assumed parameter is set to a low and a high value while everything else
stays at its default. Every setting reuses the same seeds (common random
numbers), so differences come from the parameter, not from luck.

    python run_sensitivity.py              # 60 classes per method, room and setting
    python run_sensitivity.py --runs 20    # quicker

Writes outputs/sensitivity.csv and outputs/sensitivity.md.
"""
import argparse
import copy
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


def _one(job):
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


def mmss(s):
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def main():
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
        rows = list(ex.map(_one, jobs, chunksize=4))
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


if __name__ == "__main__":
    main()
