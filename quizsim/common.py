"""Shared pieces: parameters, the class set-up, walking, recording."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import yaml

from .search import sample_per_sheet

# ---- student display states (also used by the renderer) ----
WAITING = 0     # hasn't got their quiz yet
SEARCHING = 1   # flicking through a stack / being called
GOT = 2         # has their quiz
CARRYING = 3    # walking with a stack
MISSED = 4      # ends without their quiz (missed it, or gave up)
GONE = 5        # has left the room

STATE_NAMES = {WAITING: "waiting", SEARCHING: "searching", GOT: "has quiz",
               CARRYING: "carrying stack", MISSED: "no quiz", GONE: "left"}


def load_params(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def sample_speeds(rng, n, P) -> np.ndarray:
    """Walking speeds in m/s: Normal(1.34, 0.26) free speed (Weidmann, 1993),
    clipped, then scaled by an indoor factor for a furnished room."""
    w = P["walking"]
    v = rng.normal(w["speed_mean"], w["speed_sd"], n)
    v = np.clip(v, w["speed_min"], w["speed_max"])
    return v * w["indoor_factor"]


@dataclass
class ClassSetup:
    home: list           # seat cell of each present student
    group: list          # table / half-row of each student
    order: list          # shuffled quiz ids (0..n_present-1 are present students)
    speeds: np.ndarray   # walking speed, students 0..N-1 then the lecturer at index N
    b: np.ndarray        # seconds per sheet, one per student
    rng: np.random.Generator   # for everything that happens during the method
    rank: list = None          # position of each student's seat on the passing route


def setup_class(room, P, seed) -> ClassSetup:
    """Everything that should be identical across methods for a given seed
    (common random numbers; Law, 2015): seating, the shuffle, people's speeds."""
    rng = np.random.default_rng(seed)
    N, Q = P["class"]["n_present"], P["class"]["n_quizzes"]
    idx = rng.choice(len(room.seats), N, replace=False)
    home = [room.seats[i] for i in idx]
    group = [room.seat_group[i] for i in idx]
    order = [int(x) for x in rng.permutation(Q)]
    speeds = sample_speeds(rng, N + 1, P)
    b = sample_per_sheet(rng, N, P["search"])
    return ClassSetup(home, group, order, speeds, b, np.random.default_rng([seed, 7]))


def step_length(a, b, cell) -> float:
    return cell * (math.sqrt(2.0) if (a[0] != b[0] and a[1] != b[1]) else 1.0)


def near_cells(room, target, reach, avoid=frozenset(), no_narrow=False):
    """Free cells within `reach` metres of a seated person."""
    out = []
    r = int(np.ceil(reach / room.cell))
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            c = (target[0] + dx, target[1] + dy)
            if c == target or not room.free(c) or c in avoid:
                continue
            if no_narrow and room.narrow[c]:
                continue
            if room.dist(c, target) <= reach:
                out.append(c)
    return out


@dataclass
class Walker:
    """A person following a precomputed grid path, one cell at a time."""
    cell: tuple
    speed: float
    path: list = field(default_factory=list)
    progress: float = 0.0
    waited: float = 0.0

    def go(self, path):
        self.path = list(path[1:]) if path else []
        self.progress = 0.0
        self.waited = 0.0

    @property
    def arrived(self) -> bool:
        return not self.path

    def advance(self, dt, cell_size, occupied: dict, me) -> bool:
        """Move along the path. `occupied` maps cell -> agent id. Returns True if blocked."""
        self.progress += self.speed * dt
        while self.path:
            nxt = self.path[0]
            L = step_length(self.cell, nxt, cell_size)
            if self.progress < L:
                return False
            owner = occupied.get(nxt)
            if owner is not None and owner != me:
                self.progress = L
                self.waited += dt
                return True
            if occupied.get(self.cell) == me:
                del occupied[self.cell]
            occupied[nxt] = me
            self.cell = nxt
            self.path.pop(0)
            self.progress -= L
            self.waited = 0.0
        return False


def move_all(room, walkers, ids, dt, occupied, static_avoid, homes=None):
    """Advance every walker with a path; re-plan around a blocker after 2 s.
    If someone has settled on the goal cell itself, switch to the nearest free
    cell next to it (unless the goal is the walker's own seat)."""
    for i in ids:
        w = walkers[i]
        if not w.path:
            continue
        blocked = w.advance(dt, room.cell, occupied, i)
        if blocked:
            nxt = w.path[0]
            o = occupied.get(nxt)
            if o is not None and o < len(walkers) and walkers[o].path and walkers[o].path[0] == w.cell:
                # two people heading into each other's cell: they step past each other
                occupied[w.cell], occupied[nxt] = o, i
                walkers[o].cell, w.cell = w.cell, nxt
                walkers[o].path.pop(0)
                w.path.pop(0)
                w.progress = walkers[o].progress = 0.0
                w.waited = walkers[o].waited = 0.0
                continue
        if blocked and w.waited > 2.0:
            goal = w.path[-1]
            avoid = static_avoid(i) | {c for c, o in occupied.items() if o != i}
            if goal in avoid and not (homes and homes.get(i) == goal):
                alt = [n for n, _ in room.neighbours(goal) if n not in avoid]
                if alt:
                    goal = min(alt, key=lambda c: room.dist(c, w.cell))
            p = room.path(w.cell, [goal], avoid=avoid - {goal})
            if p:
                w.go(p)
            else:
                w.waited = 0.0


class Recorder:
    """One snapshot per tick for the renderer (skipped during Monte Carlo runs)."""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.t, self.xy, self.state, self.teacher = [], [], [], []
        self.stack_xy, self.stack_n, self.returned, self.unclaimed = [], [], [], []

    def snap(self, t, xy, state, teacher_xy, stack_xy, stack_n, returned, unclaimed):
        if not self.enabled:
            return
        self.t.append(t)
        self.xy.append(np.asarray(xy, dtype=np.float32))
        self.state.append(np.asarray(state, dtype=np.int8))
        self.teacher.append(teacher_xy)
        self.stack_xy.append(np.asarray(stack_xy, dtype=np.float32).reshape(-1, 2))
        self.stack_n.append(np.asarray(stack_n))
        self.returned.append(returned)
        self.unclaimed.append(unclaimed)

    def arrays(self) -> dict | None:
        if not self.enabled:
            return None
        return {
            "t": np.array(self.t), "xy": np.stack(self.xy), "state": np.stack(self.state),
            "teacher": np.array(self.teacher, dtype=np.float32),
            "stack_xy": np.stack(self.stack_xy), "stack_n": np.stack(self.stack_n),
            "returned": np.array(self.returned), "unclaimed": np.array(self.unclaimed),
        }


def finish_metrics(m, N, Q):
    """Fill in the shared metrics (METHODS.md §5)."""
    m["n_present"], m["n_quizzes"] = N, Q
    m["unclaimed"] = N - m["returned"]
    m["leftovers"] = Q - m["returned"]
    m["exposure_mean"] = m.get("others_seen", 0) / N
    m["distraction_min"] = m.get("distraction_s", 0.0) / 60
    m["student_time_min"] = m.get("student_time_s", 0.0) / 60
    return m
