"""Method 4: the lecturer calls each name and walks the quiz to the student.

Per sheet, in stack order (METHODS.md §4):
1. Read the name: call_time, plus a repeat with probability p_repeat (up to max_repeats).
2. Absent student -> silence for absent_wait, sheet stays in hand (leftover).
   A present student fails to recognise their name with probability p_no_response
   (treated the same way; that student ends without their quiz).
3. Otherwise a hand goes up after response_time and the lecturer walks over.
   The lecturer can't squeeze into the gaps behind bench seats (G24): if the
   student is out of reach, the lecturer hands it to the nearest reachable
   point and it is passed along the bench (pass_time per seat). The lecturer
   moves on straight away.
4. The next name is read from wherever the lecturer is standing.
The whole return is teaching time lost.
"""
from __future__ import annotations

import numpy as np

from .common import (GOT, MISSED, SEARCHING, WAITING, Recorder, Walker, finish_metrics,
                     move_all, near_cells, setup_class)


def _hand_point(room, seat, reach, avoid, narrow_set):
    """Where the lecturer stands to hand a quiz to `seat`, and how many seated passes it needs."""
    direct = near_cells(room, seat, reach, avoid, no_narrow=True)
    if direct:
        return direct, 0
    best = None
    for x in range(room.nx):
        for y in range(room.ny):
            c = (x, y)
            if not room.free(c) or c in avoid or c in narrow_set:
                continue
            d = room.dist(c, seat)
            if best is None or d < best[0]:
                best = (d, c)
    d, c = best
    return [c], max(1, int(round((d - 0.6) / 0.8)))


def simulate_calling(room, P, seed, method="calling", record=False):
    cs = setup_class(room, P, seed)
    rng = cs.rng
    CA, H = P["calling"], P["handover"]
    N, Q = P["class"]["n_present"], P["class"]["n_quizzes"]
    dt = P["sim"]["dt"]
    home = cs.home
    T = N
    walkers = [Walker(home[i], cs.speeds[i]) for i in range(N)]
    walkers.append(Walker(room.teaching_cell, cs.speeds[N]))
    occupied = {home[i]: i for i in range(N)}
    occupied[room.teaching_cell] = T
    seated = set(home)
    narrow_set = {tuple(map(int, c)) for c in np.argwhere(room.narrow)}
    t_avoid = seated | narrow_set

    pile = list(cs.order)
    got = [False] * N
    missed = [False] * N
    called = [False] * N
    passes = []                         # [time left, student] quizzes travelling along a bench
    m = dict(method=method, room=room.short_name, seed=seed, returned=0, n_stacks=1,
             teaching_lost_s=0.0, distraction_s=0.0, others_seen=0, after_class_s=0.0,
             repeats=0, bench_passes=0, stood_up=0, peak_busy=0)

    state, timer, cur = "next", 0.0, None
    t, t_done = 0.0, None
    rec = Recorder(record)
    max_t = P["sim"]["max_time"]

    while t < max_t:
        if state != "idle":
            m["teaching_lost_s"] += dt
        timer -= dt
        if state == "next":
            if pile:
                cur = pile.pop(0)
                reps = 0
                while reps < CA["max_repeats"] and rng.random() < CA["p_repeat"]:
                    reps += 1
                m["repeats"] += reps
                state, timer = "call", CA["call_time"] * (1 + reps)
                if cur < N:
                    called[cur] = True
            else:
                walkers[T].go(room.path(walkers[T].cell, [room.teaching_cell], avoid=t_avoid))
                state = "return"
        elif state == "call" and timer <= 0:
            if cur >= N or rng.random() < CA["p_no_response"]:
                if cur < N:
                    missed[cur] = True
                state, timer = "next_after", CA["absent_wait"]
            else:
                state, timer = "respond", CA["response_time"]
                m["distraction_s"] += CA["response_time"]
        elif state == "next_after" and timer <= 0:
            state = "next"
        elif state == "respond" and timer <= 0:
            goals, n_pass = _hand_point(room, home[cur], CA["lecturer_reach"],
                                        seated - {walkers[T].cell}, narrow_set)
            walkers[T].go(room.path(walkers[T].cell, goals, avoid=t_avoid - set(goals)))
            state = "walk"
            cur_pass = n_pass
        elif state == "walk" and walkers[T].arrived:
            state, timer = "give", H["time"]
        elif state == "give" and timer <= 0:
            m["distraction_s"] += H["time"]
            if cur_pass == 0:
                got[cur] = True
                m["returned"] += 1
            else:
                passes.append([cur_pass * CA["pass_time"], cur])
                m["bench_passes"] += cur_pass
                m["distraction_s"] += 2 * cur_pass * CA["pass_time"]
            state = "next"
        elif state == "return" and walkers[T].arrived:
            state = "idle"

        for p in passes:
            p[0] -= dt
            if p[0] <= 0:
                got[p[1]] = True
                m["returned"] += 1
        passes = [p for p in passes if p[0] > 0]

        busy = (1 if state in ("respond", "walk", "give") else 0) + 2 * len(passes)
        m["peak_busy"] = max(m["peak_busy"], busy)
        move_all(room, walkers, [T], dt, occupied, lambda i: t_avoid)

        if record:
            st = [GOT if got[i] else MISSED if missed[i] else
                  SEARCHING if (called[i] and i == cur and state in ("call", "respond", "walk", "give"))
                  else WAITING for i in range(N)]
            txy = room.centre(walkers[T].cell)
            rec.snap(t, [room.centre(h) for h in home], st, txy, [txy], [len(pile)],
                     m["returned"], sum(missed))

        t += dt
        if state == "idle" and not passes:
            t_done = t
            break

    m["t_done"] = t_done if t_done is not None else max_t
    m["timed_out"] = t_done is None
    m["student_time_s"] = m["distraction_s"]
    return rec.arrays(), finish_metrics(m, N, Q)
