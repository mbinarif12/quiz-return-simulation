"""How long a student takes to find their own quiz in a stack, and whether they find it.

The model (written out with worked examples in METHODS.md):

* The stack is a real, physically shuffled list of quiz ids. A student flicks
  through it from the top. Their sheet's position k therefore follows from the
  shuffle itself: every position 1..n is equally likely, so E[k] = (n + 1) / 2.
* Checking stops when they reach their sheet (serial self-terminating search;
  Treisman & Gelade, 1980; Wolfe, 1998). Time = a + b * (sheets checked).
* a = setup time (pick up the stack, start flicking).
  b = time per sheet. Each student has their own b, drawn once from a
  log-normal distribution (response times are right-skewed; Luce, 1986).
* When they reach their sheet they flick past it with probability q (a miss).
  They then check the rest of the stack without finding it.
* If the student knows their sheet must be in this stack (they are holding all
  the unclaimed sheets) they go through once more, up to `max_passes` passes.
  The stack keeps its order, so on the second pass their sheet is at the same k.
  If their sheet may be in another stack, they make one pass and hand it on.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class SearchResult:
    found: bool          # did they take their sheet out?
    checked: int         # sheets looked at, counting repeats on a second pass
    time: float          # seconds spent
    passes: int          # passes through the stack
    others_seen: int     # distinct sheets of OTHER students looked at (privacy exposure)


def lognormal_params(mean: float, cv: float) -> tuple[float, float]:
    """mu, sigma of a log-normal with the given mean and coefficient of variation."""
    sigma = math.sqrt(math.log(1.0 + cv * cv))
    mu = math.log(mean) - sigma * sigma / 2.0
    return mu, sigma


def sample_per_sheet(rng, n: int, S: dict) -> np.ndarray:
    """One b (seconds per sheet) per student."""
    mu, sigma = lognormal_params(S["per_sheet_mean"], S["per_sheet_cv"])
    return rng.lognormal(mu, sigma, n)


def search(rng, stack: list, owner: int, b: float, S: dict, certain: bool) -> SearchResult:
    """Student `owner` searches `stack` (top of the stack = index 0).

    certain = True when the student knows their sheet must be in this stack,
    which allows a second pass after a miss.
    """
    n = len(stack)
    a, q = S["base_time"], S["p_miss"]
    max_passes = S["max_passes"] if certain else 1

    if owner in stack:
        k = stack.index(owner) + 1                     # position follows from the shuffle
        checked = 0
        for p in range(1, max_passes + 1):
            if rng.random() >= q:                      # spotted it
                checked += k
                others = (n - 1) if p > 1 else (k - 1)
                return SearchResult(True, checked, a + b * checked, p, others)
            checked += n                               # flicked past it, checked the rest
        return SearchResult(False, checked, a + b * checked, max_passes, n - 1)

    checked = n * max_passes                           # not in this stack: check every sheet
    return SearchResult(False, checked, a + b * checked, max_passes, n)
