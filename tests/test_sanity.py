"""Sanity checks on whole simulated classes, for every method and room:
every quiz is accounted for, nobody is left behind, nobody shares a grid cell.

Run with:  python tests/test_sanity.py   (or python -m pytest -q tests)"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from quizsim.common import load_params  # noqa: E402
from quizsim.layout import load_room  # noqa: E402
from quizsim.methods import METHODS, run  # noqa: E402

ROOMS = ["room1_science_east.yaml", "g24_agriculture.yaml"]
P = load_params(os.path.join(ROOT, "config", "params.yaml"))
SEEDS = range(3)


def _no_overlap(sim, cell):
    xy = np.concatenate([sim["xy"], sim["teacher"][:, None, :]], axis=1)
    for k in range(0, len(xy), 5):
        pts = xy[k][~np.isnan(xy[k][:, 0])]
        keys = np.floor(pts / cell + 1e-6).astype(int)
        assert len({tuple(p) for p in keys}) == len(keys), f"two people in one cell at tick {k}"


def check(method, room_file, seed):
    room = load_room(os.path.join(ROOT, "config", "rooms", room_file))
    sim, m = run(method, room, P, seed, record=True)
    tag = f"{method} / {room.short_name} / seed {seed}"
    assert not m["timed_out"], f"{tag}: did not finish"
    assert m["returned"] + m["unclaimed"] == m["n_present"], tag
    assert m["leftovers"] == m["n_quizzes"] - m["returned"], tag
    assert m["unclaimed"] >= 0 and m["returned"] <= m["n_present"], tag
    assert sim["returned"][-1] == m["returned"], tag
    _no_overlap(sim, room.cell)
    return m


def test_all_methods():
    for method in METHODS:
        for rf in ROOMS:
            for seed in SEEDS:
                check(method, rf, seed)


def test_common_random_numbers():
    """Same seed -> same seating in every method, so methods are compared on identical classes."""
    room = load_room(os.path.join(ROOT, "config", "rooms", ROOMS[0]))
    first = None
    for method in METHODS:
        sim, _ = run(method, room, P, 5, record=True)
        xy0 = sim["xy"][0]
        if first is None:
            first = xy0
        assert np.allclose(first, xy0, equal_nan=True), method


if __name__ == "__main__":
    test_all_methods()
    test_common_random_numbers()
    print("all checks passed")
