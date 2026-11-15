"""Check the search code against the probability maths in METHODS.md.

Each check runs the real `search()` function many times on freshly shuffled
stacks and compares the averages with the formula. Run:

    python tests/test_search_math.py      # prints a formula-vs-simulation table
    python -m pytest -q tests             # same checks as pass/fail tests
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from quizsim.search import sample_per_sheet, search  # noqa: E402

TRIALS = 200_000
BASE = {"base_time": 3.0, "per_sheet_mean": 0.6, "per_sheet_cv": 0.3, "p_miss": 0.02, "max_passes": 2}


def _one_stack(n, S, seed=1):
    """Owner 0 searches a shuffled stack of n sheets that contains their sheet."""
    rng = np.random.default_rng(seed)
    pos, checked, found, times = [], [], [], []
    b = sample_per_sheet(rng, TRIALS, S)
    for t in range(TRIALS):
        stack = list(rng.permutation(n))
        pos.append(stack.index(0) + 1)
        r = search(rng, stack, 0, b[t], S, certain=True)
        checked.append(r.checked)
        found.append(r.found)
        times.append(r.time)
    return np.array(pos), np.array(checked), np.array(found), np.array(times)


def _many_stacks(total, n_stacks, S, seed=2):
    """Sheets split at random into equal stacks that reach the owner in random order."""
    rng = np.random.default_rng(seed)
    m = total // n_stacks
    needed, checked = [], []
    for _ in range(TRIALS):
        perm = list(rng.permutation(total))
        stacks = [perm[i * m:(i + 1) * m] for i in range(n_stacks)]
        c = 0
        for j, st in enumerate(stacks, start=1):        # stacks already in random order
            r = search(rng, st, 0, 0.6, S, certain=False)
            c += r.checked
            if r.found:
                break
        needed.append(j)
        checked.append(c)
    return np.array(needed), np.array(checked)


def results():
    rows = []
    n, a, bm, q = 60, BASE["base_time"], BASE["per_sheet_mean"], BASE["p_miss"]

    # 1. one shuffled stack, nobody misses (q = 0)
    S0 = dict(BASE, p_miss=0.0)
    pos, chk, fnd, tim = _one_stack(n, S0)
    Ek = (n + 1) / 2
    rows += [
        ("One stack of 60: P(your sheet is on top)", 1 / n, pos == 1),
        ("One stack of 60: P(found within first 10)", 10 / n, pos <= 10),
        ("One stack of 60: P(found within first 30)", 30 / n, pos <= 30),
        ("One stack of 60: average sheets checked", Ek, chk),
        ("One stack of 60: average search time (s)", a + bm * Ek, tim),
    ]
    counts = np.bincount(pos, minlength=n + 1)[1:]
    expected = TRIALS / n
    chi2 = float(((counts - expected) ** 2 / expected).sum())

    # 2. with misses (q = 2%) and a second pass
    pos, chk, fnd, tim = _one_stack(n, BASE, seed=3)
    E_chk = (1 - q) * Ek + q * (1 - q) * (n + Ek) + q * q * 2 * n
    rows += [
        ("With 2% misses: P(not found after 2 passes) = q²", q * q, ~fnd),
        ("With 2% misses: average sheets checked", E_chk, chk),
    ]

    # 3. four stacks of 15
    need, chk4 = _many_stacks(60, 4, S0)
    rows += [
        ("4 stacks of 15: P(your sheet is in the 1st stack you get)", 15 / 60, need == 1),
        ("4 stacks of 15: P(it's in the 2nd)", 1 / 4, need == 2),
        ("4 stacks of 15: average stacks you look through", 2.5, need),
        ("4 stacks of 15: average sheets checked", 15 * 3 / 2 + 8, chk4),
    ]
    return rows, chi2


def _mean_se(sample):
    x = np.asarray(sample, dtype=float)
    return x.mean(), x.std(ddof=1) / np.sqrt(len(x))


# ---------------- pytest ----------------
def test_formulas_match_simulation():
    rows, chi2 = results()
    # tolerance = 4 standard errors of the simulated average (a false alarm about 1 in 15,000)
    for name, formula, sample in rows:
        sim, se = _mean_se(sample)
        assert abs(sim - formula) <= 4 * se + 1e-12, \
            f"{name}: formula {formula:.4f}, simulation {sim:.4f} ± {se:.4f}"
    # every position equally likely: chi-square, 59 df, critical value at p = 0.001 is 99.6
    assert chi2 < 99.6, f"positions not uniform (chi2 = {chi2:.1f})"


if __name__ == "__main__":
    rows, chi2 = results()
    w = max(len(r[0]) for r in rows)
    print(f"{'Check':<{w}}   {'Formula':>9}   {'Simulated':>9}   {'± 1 SE':>7}")
    for name, formula, sample in rows:
        sim, se = _mean_se(sample)
        print(f"{name:<{w}}   {formula:9.4f}   {sim:9.4f}   {se:7.4f}")
    print(f"\nAll 60 positions equally likely? chi-square = {chi2:.1f} (must be < 99.6 at p = 0.001)")
    test_formulas_match_simulation()
    print("\nall checks passed")
