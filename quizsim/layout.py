"""Room geometry on a square-cell grid.

The floor is discretised into 0.4 m x 0.4 m cells, the standard cell size of
cellular-automaton pedestrian models (Burstedde et al., 2001, Physica A 295,
507-525). A cell holds at most one person.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

import numpy as np
import yaml

SQRT2 = math.sqrt(2.0)
NEIGHBOURS = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
              (-1, -1, SQRT2), (-1, 1, SQRT2), (1, -1, SQRT2), (1, 1, SQRT2)]


@dataclass
class Room:
    name: str
    short_name: str
    width: float
    depth: float
    cell: float
    nx: int
    ny: int
    blocked: np.ndarray                      # True = furniture (tables, benches, desk)
    seats: list[tuple[int, int]]             # seat cells
    door_cells: set[tuple[int, int]]
    desk_cells: set[tuple[int, int]]
    desk_rect: tuple[float, float, float, float]
    teacher_cell: tuple[int, int]
    teaching_cell: tuple[int, int]
    shapes: dict = field(default_factory=dict)  # for drawing only
    seat_group: list = field(default_factory=list)   # table / half-row id of each seat
    narrow: np.ndarray | None = None                  # gaps behind bench seats: students squeeze, lecturer can't
    doors: list = field(default_factory=list)        # one set of cells per door
    seat_rank: list = field(default_factory=list)    # position of each seat on the passing route
    group_seq: list = field(default_factory=list)    # tables / half-rows in route order

    # ---------- coordinates ----------
    def centre(self, c: tuple[int, int]) -> tuple[float, float]:
        return ((c[0] + 0.5) * self.cell, (c[1] + 0.5) * self.cell)

    def to_cell(self, x: float, y: float) -> tuple[int, int]:
        ix = min(max(int(x / self.cell), 0), self.nx - 1)
        iy = min(max(int(y / self.cell), 0), self.ny - 1)
        return ix, iy

    def dist(self, a, b) -> float:
        """Euclidean distance between two cells, in metres."""
        return math.hypot(a[0] - b[0], a[1] - b[1]) * self.cell

    def inside(self, c) -> bool:
        return 0 <= c[0] < self.nx and 0 <= c[1] < self.ny

    def free(self, c) -> bool:
        return self.inside(c) and not self.blocked[c]

    # ---------- movement graph ----------
    def neighbours(self, c):
        x, y = c
        for dx, dy, w in NEIGHBOURS:
            n = (x + dx, y + dy)
            if not self.free(n):
                continue
            if dx and dy and (self.blocked[x + dx, y] or self.blocked[x, y + dy]):
                continue                      # no squeezing diagonally past furniture corners
            yield n, w

    def floor_field(self, targets, avoid=frozenset()) -> np.ndarray:
        """Static floor field: walking distance (in cells) to the nearest target.
        Same idea as the static field S_ij of Burstedde et al. (2001)."""
        field_ = np.full((self.nx, self.ny), np.inf)
        heap = []
        for t in targets:
            field_[t] = 0.0
            heap.append((0.0, t))
        heapq.heapify(heap)
        while heap:
            d, c = heapq.heappop(heap)
            if d > field_[c]:
                continue
            for n, w in self.neighbours(c):
                if n in avoid:
                    continue
                nd = d + w
                if nd < field_[n]:
                    field_[n] = nd
                    heapq.heappush(heap, (nd, n))
        return field_

    def path(self, start, goals, avoid=frozenset()):
        """Shortest 8-connected path from start to any goal cell (Dijkstra)."""
        goals = set(goals)
        if start in goals:
            return [start]
        dist = {start: 0.0}
        prev = {}
        heap = [(0.0, start)]
        while heap:
            d, c = heapq.heappop(heap)
            if c in goals:
                out = [c]
                while c in prev:
                    c = prev[c]
                    out.append(c)
                return out[::-1]
            if d > dist[c]:
                continue
            for n, w in self.neighbours(c):
                if n in avoid and n not in goals:
                    continue
                nd = d + w
                if nd < dist.get(n, math.inf):
                    dist[n] = nd
                    prev[n] = c
                    heapq.heappush(heap, (nd, n))
        return None


def _wall_cells(nx, ny, cell, wall, a, b):
    out = set()
    if wall in ("front", "back"):
        iy = 0 if wall == "front" else ny - 1
        for ix in range(nx):
            if a <= (ix + 0.5) * cell <= b:
                out.add((ix, iy))
    else:
        ix = 0 if wall == "left" else nx - 1
        for iy in range(ny):
            if a <= (iy + 0.5) * cell <= b:
                out.add((ix, iy))
    return out


def load_room(path: str, cell: float = 0.4) -> Room:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    nx = int(round(cfg["width"] / cell))
    ny = int(round(cfg["depth"] / cell))
    blocked = np.zeros((nx, ny), dtype=bool)
    xs = (np.arange(nx) + 0.5) * cell
    ys = (np.arange(ny) + 0.5) * cell
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    seats: list[tuple[int, int]] = []
    seat_group: list[int] = []
    narrow = np.zeros((nx, ny), dtype=bool)
    shapes = {"circles": [], "rects": [], "decor": cfg.get("decor", []), "doors": cfg["doors"]}

    def snap(x, y):
        # small epsilon so points that fall exactly on a cell boundary snap consistently
        return (min(max(int(x / cell + 1e-6), 0), nx - 1),
                min(max(int(y / cell + 1e-6), 0), ny - 1))

    if "round_tables" in cfg:
        rt = cfg["round_tables"]
        for cx, cy in rt["centres"]:
            blocked |= (X - cx) ** 2 + (Y - cy) ** 2 < rt["radius"] ** 2
            shapes["circles"].append((cx, cy, rt["radius"]))
        for g, (cx, cy) in enumerate(rt["centres"]):
            n = rt["seats_per_table"]
            for k in range(n):
                a = 2 * math.pi * (k + 0.5) / n
                c = snap(cx + rt["seat_radius"] * math.cos(a), cy + rt["seat_radius"] * math.sin(a))
                if not blocked[c] and c not in seats:
                    seats.append(c)
                    seat_group.append(g)

    if "bench_rows" in cfg:
        br = cfg["bench_rows"]
        for r in range(br["n_rows"]):
            y0 = br["first_bench_y"] + r * br["row_pitch"]
            y1 = y0 + br["bench_depth"]
            for bi, bank in enumerate(br["banks"]):
                blocked |= (X >= bank["x0"]) & (X < bank["x1"]) & (Y >= y0) & (Y < y1)
                if r < br["n_rows"] - 1:     # seat line + gap up to the next bench
                    narrow |= (X >= bank["x0"]) & (X < bank["x1"]) & (Y >= y1) & (Y < y0 + br["row_pitch"])
                shapes["rects"].append((bank["x0"], y0, bank["x1"] - bank["x0"], y1 - y0, "bench"))
                for i in range(bank["seats"]):
                    seats.append(snap(bank["x0"] + br["seat_spacing"] * (i + 0.5), y1 + cell / 2))
                    seat_group.append(r * len(br["banks"]) + bi)

    d = cfg["desk"]
    desk_mask = (X >= d["x0"]) & (X < d["x1"]) & (Y >= d["y0"]) & (Y < d["y1"])
    blocked |= desk_mask
    desk_cells = {tuple(map(int, c)) for c in np.argwhere(desk_mask)}
    shapes["rects"].append((d["x0"], d["y0"], d["x1"] - d["x0"], d["y1"] - d["y0"], "desk"))

    door_list = [_wall_cells(nx, ny, cell, door["wall"], door["from"], door["to"]) for door in cfg["doors"]]
    doors = set().union(*door_list)

    room = Room(
        name=cfg["name"], short_name=cfg.get("short_name", cfg["name"]),
        width=cfg["width"], depth=cfg["depth"], cell=cell, nx=nx, ny=ny,
        blocked=blocked, seats=seats, door_cells=doors, desk_cells=desk_cells,
        desk_rect=(d["x0"], d["y0"], d["x1"], d["y1"]),
        teacher_cell=snap(*cfg["teacher_spot"]), teaching_cell=snap(*cfg["teaching_spot"]),
        shapes=shapes, seat_group=seat_group, narrow=narrow & ~blocked, doors=door_list,
    )
    room.group_seq, room.seat_rank = passing_route(room, cfg)
    return room


def passing_route(room, cfg):
    """A fixed route through every seat: the order a stack is passed in.

    Benches (G24): snake through each bank, row by row, so the stack stays on a
    bench and moves to the next row at the row's end. The left bank runs front
    to back and ends at the aisle; the stack crosses the aisle once and the
    right bank runs back to front.
    Round tables: tables in a snake (front row left to right, back row right to
    left); round each table starting at the seat nearest the previous table and
    turning the way that ends nearest the next table.
    Returns (group order, rank of each seat).
    """
    seats, grp = room.seats, room.seat_group
    xy = {i: room.centre(c) for i, c in enumerate(seats)}
    order = []
    if "bench_rows" in cfg:
        br = cfg["bench_rows"]
        nb, nr = len(br["banks"]), br["n_rows"]
        group_seq = []
        for bi in range(nb):
            rows = list(range(nr)) if bi % 2 == 0 else list(range(nr - 1, -1, -1))
            for k, r in enumerate(rows):
                g = r * nb + bi
                inc = (nr - 1 - k) % 2 == 0
                members = sorted((i for i in range(len(seats)) if grp[i] == g),
                                 key=lambda i: xy[i][0], reverse=not inc)
                order += members
                group_seq.append(g)
    else:
        centres = cfg["round_tables"]["centres"]
        ys = sorted({round(c[1], 1) for c in centres})
        group_seq = []
        for k, y in enumerate(ys):
            row = [g for g, c in enumerate(centres) if round(c[1], 1) == y]
            group_seq += sorted(row, key=lambda g: centres[g][0], reverse=(k % 2 == 1))
        prev = room.centre(room.teaching_cell)
        for n, g in enumerate(group_seq):
            cx, cy = centres[g]
            members = [i for i in range(len(seats)) if grp[i] == g]
            ang = {i: math.atan2(xy[i][1] - cy, xy[i][0] - cx) for i in members}
            first = min(members, key=lambda i: math.dist(xy[i], prev))
            nxt = centres[group_seq[n + 1]] if n + 1 < len(group_seq) else prev
            best = None
            for sgn in (1, -1):
                seq = sorted(members, key=lambda i: (sgn * (ang[i] - ang[first])) % (2 * math.pi))
                d = math.dist(xy[seq[-1]], nxt)
                if best is None or d < best[0]:
                    best = (d, seq)
            order += best[1]
            prev = xy[best[1][-1]]
    rank = [0] * len(seats)
    for r, i in enumerate(order):
        rank[i] = r
    return group_seq, rank
