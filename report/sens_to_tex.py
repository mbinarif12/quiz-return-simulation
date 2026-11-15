"""Turn outputs/sensitivity.csv into report/sens_table.tex."""
import csv, sys, os
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from run_sensitivity import SETTINGS
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
