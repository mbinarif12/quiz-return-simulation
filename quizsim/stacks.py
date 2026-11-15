"""Methods 1-3: stacks passed hand to hand while the lecturer keeps teaching.

  one_stack   the whole shuffled stack starts at the first seat on the passing
              route and travels along it
  two_stacks  a random 30/30 split; one stack starts at each end of the route
              and they travel in opposite directions
  per_table   one stack per occupied table (G24: per occupied half-row), placed
              by the lecturer; each goes round its table, then on to the next
              table on the route, and so on round the room

Rules shared by all three (METHODS.md §4):
* A student holds one stack at a time. Stacks that reach a busy student wait
  in front of them, in arrival order.
* A student searches a stack with the model in search.py. They are "certain"
  their sheet is in it (so a miss earns a second pass) only when it is the
  last stack they haven't seen.
* Stacks follow the room's fixed passing route (layout.passing_route): seat
  by seat along a bench or round a table, then on to the next row / table.
  Everyone on the way handles the stack; someone who already has their quiz
  just passes it on.
* On the same bench or table the hand-over is always seated (the stack slides
  past empty seats, slide_per_m extra per metre beyond arm's reach). Between
  rows or tables it is seated within reach; otherwise the holder gets up,
  walks it over, and walks back.
* When nobody further along the route still needs it, the stack is carried to
  the lecturer's desk (leftovers).
  A stack that runs out of sheets simply stops.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from .common import (CARRYING, GOT, MISSED, SEARCHING, WAITING, Recorder, Walker,
                     finish_metrics, move_all, near_cells, setup_class)
from .search import search

METHODS = ("one_stack", "two_stacks", "per_table")
DESK, GONE_STACK = -1, -2


@dataclass
class Stack:
    sheets: list
    carrier: int          # person holding it (lecturer = N), DESK, or GONE_STACK
    ended: bool = False
    leftover: bool = False   # nobody else needs it: being relayed towards the desk
    parked: bool = False     # leftovers waiting with the collector


def _initial_stacks(room, cs, N, method):
    """Return the stacks and the lecturer's hand-out plan [(stack id, student), ...]."""
    """Also returns each stack's direction along the route (+1 / -1)."""
    order = cs.order
    rank = cs.rank
    by_rank = sorted(range(N), key=lambda i: rank[i])
    if method == "one_stack":
        return [order[:]], [(0, by_rank[0])], [1]
    if method == "two_stacks":
        half = len(order) // 2
        return [order[:half], order[half:]], [(0, by_rank[0]), (1, by_rank[-1])], [1, -1]
    if method == "per_table":
        groups = [g for g in room.group_seq if g in set(cs.group)]   # occupied, in route order
        chunks = np.array_split(np.array(order), len(groups))
        stacks = [list(map(int, c)) for c in chunks]
        plan = [(k, min((i for i in range(N) if cs.group[i] == g), key=lambda i: rank[i]))
                for k, g in enumerate(groups)]
        return stacks, plan, [1] * len(groups)
    raise ValueError(method)


def simulate_stacks(room, P, seed, method, record=False):
    cs = setup_class(room, P, seed)
    rng = cs.rng
    S, H = P["search"], P["handover"]
    N, Q = P["class"]["n_present"], P["class"]["n_quizzes"]
    dt = P["sim"]["dt"]
    home, b = cs.home, cs.b
    T = N                                                     # lecturer's id
    walkers = [Walker(home[i], cs.speeds[i]) for i in range(N)]
    walkers.append(Walker(room.teaching_cell, cs.speeds[N]))
    occupied = {home[i]: i for i in range(N)}
    occupied[room.teaching_cell] = T

    cs.rank = [room.seat_rank[room.seats.index(h)] for h in home]
    rank = cs.rank
    occ_groups = [g for g in room.group_seq if g in set(cs.group)]
    stacks_l, plan, direction = _initial_stacks(room, cs, N, method)
    stacks = [Stack(s, T) for s in stacks_l]
    n_stacks = len(stacks)

    done = [False] * N
    found = [False] * N
    seen = [set() for _ in range(N)]
    queue = [deque() for _ in range(N)]
    inflight = [set() for _ in range(N)]
    task = [None] * N

    m = dict(method=method, room=room.short_name, seed=seed, returned=0, n_stacks=n_stacks,
             teaching_lost_s=0.0, distraction_s=0.0, others_seen=0, sheets_checked=0,
             walked_handovers=0, seated_handovers=0, second_passes=0, after_class_s=0.0,
             stood_up=0, peak_busy=0)

    homes_d = {i: home[i] for i in range(N)}
    desk_d = [min(room.dist(home[j], c) for c in room.desk_cells) for j in range(N)]
    collector = int(np.argmin(desk_d))       # student nearest the desk takes leftovers up
    gsize = {}
    for g in room.seat_group:
        gsize[g] = gsize.get(g, 0) + 1

    def seated(exclude=()):
        return {home[j] for j in range(N) if walkers[j].cell == home[j] and j not in exclude}

    def static_avoid(i):
        return seated(exclude=(i,)) if i < N else seated()

    def unseen(sid, i):
        return [j for j in range(N) if j != i and sid not in seen[j]
                and sid not in queue[j] and sid not in inflight[j]]

    def next_target(sid, i):
        """Next person on the route, or None when nobody further on still needs it."""
        cand = unseen(sid, i)
        if not any(not done[j] for j in cand):
            return None
        if method == "per_table":
            g_i = cs.group[i]
            same = [j for j in cand if cs.group[j] == g_i]
            if any(not done[j] for j in same):                 # keep going round this table
                return min(same, key=lambda j: (rank[j] - rank[i]) % gsize[g_i])
            k = occ_groups.index(g_i)
            for step in range(1, len(occ_groups) + 1):        # next table round the room
                g = occ_groups[(k + step) % len(occ_groups)]
                members = [j for j in cand if cs.group[j] == g]
                if any(not done[j] for j in members):         # whoever there is nearest
                    return min(members, key=lambda j: room.dist(home[i], home[j]))
            return None
        d = direction[sid]
        ahead = [j for j in cand if d * (rank[j] - rank[i]) > 0]
        if any(not done[j] for j in ahead):
            return min(ahead, key=lambda j: d * rank[j])
        behind = [j for j in cand if not done[j]]                # rare: someone was skipped
        return min(behind, key=lambda j: abs(rank[j] - rank[i]))

    def is_certain(i, sid):
        return all(o == sid or o in seen[i] or not stacks[o].sheets for o in range(n_stacks))

    def start(i, sid):
        if stacks[sid].leftover:         # leftovers being passed towards the desk
            relay(i, sid)
            return
        if done[i]:                      # already has their quiz: just pass it on
            seen[i].add(sid)
            pass_on(i, sid)
            return
        certain = is_certain(i, sid)
        res = search(rng, stacks[sid].sheets, i, b[i], S, certain)
        seen[i].add(sid)
        m["others_seen"] += res.others_seen
        m["sheets_checked"] += res.checked
        m["second_passes"] += res.passes > 1
        task[i] = dict(kind="search", sid=sid, timer=res.time, res=res, certain=certain)

    def pass_on(i, sid):
        st = stacks[sid]
        if not st.sheets:                # every sheet claimed: the stack is finished
            st.ended, st.carrier = True, GONE_STACK
            task[i] = None
            return
        j = next_target(sid, i)
        if j is None:                    # nobody else needs it: pass the leftovers forward
            st.leftover = True
            relay(i, sid)
            return
        hand_to(i, sid, j)

    def relay(i, sid):
        """Pass leftovers towards the desk, seated where possible; the student
        nearest the desk keeps them and takes them all up in one trip."""
        st = stacks[sid]
        if i == collector:
            st.parked, st.carrier = True, i
            task[i] = None
            return
        closer = [j for j in range(N) if desk_d[j] < desk_d[i] - 0.3] or [collector]
        near = [j for j in closer if room.dist(home[i], home[j]) <= H["reach"]]
        j = min(near, key=lambda j: desk_d[j]) if near else \
            min(closer, key=lambda j: room.dist(home[i], home[j]))
        hand_to(i, sid, j)

    def hand_to(i, sid, j):
        inflight[j].add(sid)
        d = room.dist(walkers[i].cell, home[j])
        same_line = cs.group[i] == cs.group[j] and walkers[i].cell == home[i]
        if d <= H["reach"] or same_line:
            slide = H["slide_per_m"] * max(0.0, d - H["reach"])   # slid along the bench / table
            task[i] = dict(kind="hand", sid=sid, to=j, timer=H["time"] + slide)
            m["seated_handovers"] += 1
        else:
            goals = near_cells(room, home[j], H["reach"], seated(exclude=(i,)))
            p = room.path(walkers[i].cell, goals, avoid=seated(exclude=(i,)))
            walkers[i].go(p)
            task[i] = dict(kind="walk", sid=sid, to=j)
            m["walked_handovers"] += 1
            m["stood_up"] += 1

    def collect_leftovers():
        """When every stack is finished or parked, the collector takes the leftovers up."""
        parked = [k for k, st in enumerate(stacks) if st.parked and not st.ended]
        if not parked or task[collector] is not None or queue[collector] or walkers[collector].path:
            return
        if not all(st.ended or st.parked for st in stacks):
            return
        i = collector
        goals = [c for c in near_cells(room, min(room.desk_cells, key=lambda c: room.dist(c, home[i])),
                                       1.0, seated(exclude=(i,))) if c not in room.desk_cells]
        walkers[i].go(room.path(walkers[i].cell, goals, avoid=seated(exclude=(i,))))
        task[i] = dict(kind="to_desk", sids=parked)
        m["stood_up"] += 1

    def deliver(sid, j):
        inflight[j].discard(sid)
        queue[j].append(sid)
        stacks[sid].carrier = j

    def go_home(i):
        if walkers[i].cell != home[i]:
            walkers[i].go(room.path(walkers[i].cell, [home[i]], avoid=seated(exclude=(i,))))

    # lecturer's script: walk to each first holder, hand over, walk back
    tplan = deque(plan)
    tstate = None                        # None | "walk" | "give" | "return" | "idle"
    ttimer = 0.0
    tcur = None

    def teacher_next():
        nonlocal tstate, tcur
        if tplan:
            tcur = tplan.popleft()
            j = tcur[1]
            goals = near_cells(room, home[j], H["reach"], seated(), no_narrow=True) \
                or near_cells(room, home[j], H["reach"], seated())
            p = room.path(walkers[T].cell, goals, avoid=seated())
            walkers[T].go(p)
            tstate = "walk"
        else:
            walkers[T].go(room.path(walkers[T].cell, [room.teaching_cell], avoid=seated()))
            tstate = "return"

    teacher_next()
    rec = Recorder(record)
    desk_xy = room.centre(min(room.desk_cells))
    t = 0.0
    t_done = None
    max_t = P["sim"]["max_time"]

    while t < max_t:
        # ---- lecturer ----
        if tstate != "idle":
            m["teaching_lost_s"] += dt
            if tstate == "walk" and walkers[T].arrived:
                tstate, ttimer = "give", H["time"]
            elif tstate == "give":
                ttimer -= dt
                if ttimer <= 0:
                    deliver(*tcur)
                    teacher_next()
            elif tstate == "return" and walkers[T].arrived:
                tstate = "idle"

        # ---- students ----
        for i in range(N):
            tk = task[i]
            if tk is None:
                if queue[i] and not walkers[i].path and walkers[i].cell == home[i]:
                    start(i, queue[i].popleft())
                continue
            m["distraction_s"] += dt
            k = tk["kind"]
            if k == "search":
                tk["timer"] -= dt
                if tk["timer"] <= 0:
                    res = tk["res"]
                    if res.found:
                        stacks[tk["sid"]].sheets.remove(i)
                        found[i] = done[i] = True
                        m["returned"] += 1
                    elif tk["certain"]:
                        done[i] = True   # went through it twice and still missed it
                    pass_on(i, tk["sid"])
            elif k == "walk":
                if walkers[i].arrived:
                    tk["kind"], tk["timer"] = "hand", H["time"]
            elif k == "hand":
                tk["timer"] -= dt
                if tk["timer"] <= 0:
                    deliver(tk["sid"], tk["to"])
                    task[i] = None
                    go_home(i)
            elif k == "to_desk":
                if walkers[i].arrived:
                    tk["kind"], tk["timer"] = "drop", H["drop_time"]
            elif k == "drop":
                tk["timer"] -= dt
                if tk["timer"] <= 0:
                    for sid in tk["sids"]:
                        stacks[sid].ended, stacks[sid].carrier = True, DESK
                    task[i] = None
                    go_home(i)

        collect_leftovers()
        m["peak_busy"] = max(m["peak_busy"], sum(1 for x in task if x is not None))
        move_all(room, walkers, range(N + 1), dt, occupied, static_avoid, homes_d)

        # ---- record ----
        if record:
            state = []
            for i in range(N):
                tk = task[i]
                if tk and tk["kind"] == "search":
                    state.append(SEARCHING)
                elif tk and tk["kind"] in ("walk", "to_desk", "drop"):
                    state.append(CARRYING)
                elif found[i]:
                    state.append(GOT)
                elif done[i]:
                    state.append(MISSED)
                else:
                    state.append(WAITING)
            xy = [room.centre(w.cell) for w in walkers]
            sxy = [xy[st.carrier] if st.carrier >= 0 else (desk_xy if st.carrier == DESK else (np.nan, np.nan))
                   for st in stacks]
            rec.snap(t, xy[:N], state, xy[T], sxy, [len(st.sheets) for st in stacks],
                     m["returned"], sum(1 for i in range(N) if done[i] and not found[i]))

        t += dt
        if (tstate == "idle" and all(st.ended for st in stacks) and all(x is None for x in task)
                and not any(w.path for w in walkers)):
            t_done = t
            break

    m["t_done"] = t_done if t_done is not None else max_t
    m["timed_out"] = t_done is None
    if t_done is None:                   # diagnostic for debugging stuck runs
        m["stuck"] = [(i, task[i] and {k: v for k, v in task[i].items() if k != "res"},
                       walkers[i].cell, home[i], walkers[i].path[:3], list(queue[i]))
                      for i in range(N) if task[i] or queue[i] or walkers[i].path]
    m["student_time_s"] = m["distraction_s"]
    return rec.arrays(), finish_metrics(m, N, Q)
