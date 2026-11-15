"""Methods 5a / 5b: one pile, everyone collects after class.

  pile_desk  the pile is on the lecturer's desk; people leave by any door
  pile_door  the pile is on a chair beside one door; everyone leaves by that door

Rules (METHODS.md §4):
* Students pack up for Uniform(0, getup_delay_max) s, then walk to the pile
  (cellular-automaton crowd model: Burstedde et al., 2001; Kirchner &
  Schadschneider, 2002).
* At most `max_at_pile` people can handle the pile at once. When someone gets
  a turn, the pile (in its real, shuffled order) is spread into that many
  chunks. They search the chunks in random order with the model in
  search.py, waiting `swap_time` for each further chunk. They are certain on
  the last chunk, so a miss there earns a second pass (METHODS.md §3.4–3.5).
* Anyone who has queued longer than their patience gives up and leaves
  without their quiz.
* Done when everyone has left and the leftovers are with the lecturer (for
  the door version, after the lecturer has walked over to collect them).
"""
from __future__ import annotations

import math

import numpy as np

from .common import (GONE, GOT, MISSED, SEARCHING, WAITING, Recorder, Walker,
                     finish_metrics, setup_class, step_length)
from .search import search

METHODS = ("pile_desk", "pile_door")


def pile_spot(room, where, radius, door_index=0):
    """Point where the pile sits, the cells people search from, and the exit cells."""
    if where == "desk":
        x0, y0, x1, y1 = room.desk_rect
        pt = ((x0 + x1) / 2, y1 + 0.1)
        exits = room.door_cells
        avoid = set()
    else:
        door = sorted(room.doors[door_index])
        cx = np.mean([room.centre(c)[0] for c in door])
        cy = np.mean([room.centre(c)[1] for c in door])
        half = len(door) * room.cell / 2
        if door[0][1] == 0:                 # front wall: pile beside the door, towards the room
            sx = 1 if cx < room.width / 2 else -1
            pt = (cx + sx * (half + 0.8), 0.6)
        else:                               # side wall
            sy = 1 if cy < room.depth / 2 else -1
            x_in = 0.6 if door[0][0] == 0 else room.width - 0.6
            pt = (x_in, cy + sy * (half + 0.8))
        exits = set(door)
        avoid = {c for c in np.ndindex(room.nx, room.ny)
                 if min(room.dist(c, d) for d in door) < 0.8}
    acc = set()
    for c in np.ndindex(room.nx, room.ny):
        if not room.free(c) or c in avoid or c == room.teacher_cell:
            continue
        x, y = room.centre(c)
        if where == "desk":
            # only the spots right at the desk, on the students' side
            x0, y0, x1, y1 = room.desk_rect
            if y >= y1 and y - y1 <= room.cell and x0 - room.cell <= x <= x1 + room.cell:
                acc.add(c)
        elif math.hypot(x - pt[0], y - pt[1]) <= radius:
            acc.add(c)
    return pt, acc, exits


def simulate_pile(room, P, seed, method, record=False):
    where = "desk" if method == "pile_desk" else "door"
    cs = setup_class(room, P, seed)
    rng = cs.rng
    PP, S = P["pile"], P["search"]
    N, Q = P["class"]["n_present"], P["class"]["n_quizzes"]
    dt, cell = P["sim"]["dt"], room.cell

    pos = list(cs.home)
    speed = cs.speeds[:N]
    getup = rng.uniform(0, PP["getup_delay_max"], N)
    patience = rng.lognormal(math.log(PP["patience_median"]), PP["patience_sigma"], N)

    pt, acc, exits = pile_spot(room, where, PP["access_radius"], PP["door_index"])
    lecturer = frozenset({room.teacher_cell})     # the lecturer sits behind the desk: route around them
    f_pile = room.floor_field(acc, avoid=lecturer)
    f_exit = room.floor_field(exits, avoid=lecturer)

    mode = ["seated"] * N               # seated -> to_pile -> search -> exit -> gone
    got = [False] * N
    progress = np.zeros(N)
    timer = np.zeros(N)
    outcome = [None] * N
    occupied = {pos[i]: i for i in range(N)}
    occupied[room.teacher_cell] = N
    pile = list(cs.order)

    m = dict(method=method, room=room.short_name, seed=seed, returned=0, n_stacks=1,
             teaching_lost_s=0.0, distraction_s=0.0, others_seen=0, sheets_checked=0,
             gave_up=0, missed=0, max_queue=0, student_time_s=0.0, stood_up=N, peak_busy=0)

    def try_move(i, field_, can_swap):
        """Random-sequential CA step towards lower floor-field values."""
        here = pos[i]
        progress[i] += speed[i] * dt
        options = []
        for n, _ in room.neighbours(here):
            if field_[n] < field_[here] - 1e-9:
                options.append((field_[n] + 1e-3 * rng.random(), n))
        options.sort()
        for _, n in options:
            L = step_length(here, n, cell)
            if progress[i] < L:
                return
            o = occupied.get(n)
            if o is None:
                del occupied[here]
                occupied[n] = i
                pos[i] = n
                progress[i] -= L
                return
            if can_swap and o < N and mode[o] == "to_pile" and rng.random() < PP["p_swap"]:
                pos[i], pos[o] = n, here     # a leaver squeezes past someone queueing
                occupied[n], occupied[here] = i, o
                progress[i] -= L
                return
        if progress[i] >= cell and rng.random() < 0.2:   # stuck: shuffle sideways
            side = [n for n, _ in room.neighbours(here)
                    if n not in occupied and abs(field_[n] - field_[here]) < 1.01 and field_[n] < np.inf]
            if side:
                n = side[rng.integers(len(side))]
                del occupied[here]
                occupied[n] = i
                pos[i] = n
                progress[i] = 0.0
                return
        progress[i] = min(progress[i], cell * 1.5)

    def start_search(i):
        """Spread the pile into chunks and work through them (METHODS.md §3.5)."""
        k = max(1, min(PP["max_at_pile"], len(pile)))
        chunks = [list(map(int, c)) for c in np.array_split(np.array(pile, dtype=int), k) if len(c)]
        order = rng.permutation(len(chunks))
        total = 0.0
        found = False
        for n_done, ci in enumerate(order):
            res = search(rng, chunks[ci], i, cs.b[i], S, certain=(n_done == len(order) - 1))
            total += res.time + (PP["swap_time"] if n_done else 0.0)
            m["others_seen"] += res.others_seen
            m["sheets_checked"] += res.checked
            if res.found:
                found = True
                break
        timer[i] = total
        outcome[i] = found

    # lecturer: sits at the desk; in the door version walks to the pile at the end
    teacher = Walker(room.teacher_cell, cs.speeds[N])
    t_state = "wait"
    t = 0.0
    t_done = None
    rec = Recorder(record)
    max_t = P["sim"]["max_time"]

    while t < max_t:
        n_search = sum(1 for md in mode if md == "search")
        for i in rng.permutation(N):
            md = mode[i]
            if md == "seated":
                if t >= getup[i]:
                    mode[i] = "to_pile"
            elif md == "to_pile":
                if t - getup[i] > patience[i]:
                    mode[i] = "exit"
                    m["gave_up"] += 1
                elif pos[i] in acc and n_search < PP["max_at_pile"]:
                    start_search(i)
                    mode[i] = "search"
                    n_search += 1
                elif pos[i] not in acc:
                    try_move(i, f_pile, False)
            elif md == "search":
                timer[i] -= dt
                if timer[i] <= 0:
                    if outcome[i]:
                        pile.remove(i)
                        got[i] = True
                        m["returned"] += 1
                    else:
                        m["missed"] += 1
                    mode[i] = "exit"
                    n_search -= 1
            elif md == "exit":
                if pos[i] in exits:
                    mode[i] = "gone"
                    del occupied[pos[i]]
                else:
                    try_move(i, f_exit, True)

        active = sum(1 for md in mode if md in ("to_pile", "search", "exit"))
        m["student_time_s"] += active * dt
        m["peak_busy"] = max(m["peak_busy"], active)
        m["max_queue"] = max(m["max_queue"], sum(1 for md in mode if md == "to_pile"))

        if all(md == "gone" for md in mode):
            if where == "desk":
                t_done = t
                break
            if t_state == "wait":
                goals = [c for c in sorted(acc, key=lambda c: math.hypot(room.centre(c)[0] - pt[0],
                                                                          room.centre(c)[1] - pt[1]))[:3]]
                teacher.go(room.path(teacher.cell, goals))
                t_state = "walk"
            elif t_state == "walk":
                teacher.advance(dt, cell, {}, N)
                if teacher.arrived:
                    t_done = t
                    break

        if record:
            st = [GONE if mode[i] == "gone" else GOT if got[i] else
                  MISSED if mode[i] == "exit" else SEARCHING if mode[i] == "search" else WAITING
                  for i in range(N)]
            xy = [room.centre(pos[i]) if mode[i] != "gone" else (np.nan, np.nan) for i in range(N)]
            rec.snap(t, xy, st, room.centre(teacher.cell), [pt], [len(pile)],
                     m["returned"], m["gave_up"] + m["missed"])
        t += dt

    m["t_done"] = t_done if t_done is not None else max_t
    m["timed_out"] = t_done is None
    m["after_class_s"] = m["t_done"]
    return rec.arrays(), finish_metrics(m, N, Q)
