"""The five ways of handing quizzes back, and one entry point for all of them.

  methods 1-3  stacks passed hand to hand   simulate_stacks
  method 4     calling names                simulate_calling
  method 5     pile on the desk             simulate_pile
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from .common import (CARRYING, GONE, GOT, MISSED, SEARCHING, WAITING, Recorder, Walker,
                     finish_metrics, move_all, near_cells, setup_class, step_length)
from .search import search


# ============================================================================
# Methods 1-3: stacks passed hand to hand while the lecturer keeps teaching.
#
#   one_stack   the whole shuffled stack starts at the first seat on the passing
#               route and travels along it
#   two_stacks  a random 30/30 split; one stack starts at each end of the route
#               and they travel in opposite directions
#   per_table   one stack per occupied table (G24: per occupied half-row), placed
#               by the lecturer; each goes round its table, then on to the next
#               table on the route, and so on round the room
#
# Rules shared by all three (METHODS.md §4):
# * A student holds one stack at a time. Stacks that reach a busy student wait
#   in front of them, in arrival order.
# * A student searches a stack with the model in search.py. They are "certain"
#   their sheet is in it (so a miss earns a second pass) only when it is the
#   last stack they haven't seen.
# * Stacks follow the room's fixed passing route (layout.passing_route): seat
#   by seat along a bench or round a table, then on to the next row / table.
#   Everyone on the way handles the stack; someone who already has their quiz
#   just passes it on.
# * On the same bench or table the hand-over is always seated (the stack slides
#   past empty seats, slide_per_m extra per metre beyond arm's reach). Between
#   rows or tables it is seated within reach; otherwise the holder gets up,
#   walks it over, and walks back.
# * When nobody further along the route still needs it, the leftovers are passed
#   forward to the student nearest the desk, who takes them all up in one trip.
#   A stack that runs out of sheets simply stops.
# ============================================================================

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


# ============================================================================
# Method 4: the lecturer calls each name and walks the quiz to the student.
#
# Per sheet, in stack order (METHODS.md §4):
# 1. Read the name: call_time, plus a repeat with probability p_repeat (up to max_repeats).
# 2. Absent student -> silence for absent_wait, sheet stays in hand (leftover).
#    A present student fails to recognise their name with probability p_no_response
#    (treated the same way; that student ends without their quiz).
# 3. Otherwise a hand goes up after response_time and the lecturer walks over.
#    The lecturer can't squeeze into the gaps behind bench seats (G24): if the
#    student is out of reach, the lecturer hands it to the nearest reachable
#    point and it is passed along the bench (pass_time per seat). The lecturer
#    moves on straight away.
# 4. The next name is read from wherever the lecturer is standing.
# The whole return is teaching time lost.
# ============================================================================

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


# ============================================================================
# Methods 5a / 5b: one pile, everyone collects after class.
#
#   pile_desk  the pile is on the lecturer's desk; people leave by any door
#   pile_door  the pile is on a chair beside one door; everyone leaves by that door
#
# Rules (METHODS.md §4):
# * Students pack up for Uniform(0, getup_delay_max) s, then walk to the pile
#   (cellular-automaton crowd model: Burstedde et al., 2001; Kirchner &
#   Schadschneider, 2002).
# * At most `max_at_pile` people can handle the pile at once. When someone gets
#   a turn, the pile (in its real, shuffled order) is spread into that many
#   chunks. They search the chunks in random order with the model in
#   search.py, waiting `swap_time` for each further chunk. They are certain on
#   the last chunk, so a miss there earns a second pass (METHODS.md §3.4–3.5).
# * Anyone who has queued longer than their patience gives up and leaves
#   without their quiz.
# * Done when everyone has left and the leftovers are with the lecturer (for
#   the door version, after the lecturer has walked over to collect them).
# ============================================================================

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


# ============================================================================
# Registry
# ============================================================================

METHODS = {
    "one_stack":  ("1 · One stack from one end", simulate_stacks),
    "two_stacks": ("2 · Two stacks, one from each end", simulate_stacks),
    "per_table":  ("3 · One stack per table", simulate_stacks),
    "calling":    ("4 · Calling names, lecturer walks", simulate_calling),
    "pile_desk":  ("5 · Pile on my desk, after class", simulate_pile),
    # "pile_door" (pile beside a door) is still in simulate_pile but no longer compared:
    # in practice it is the same method as the pile on the desk.
}


def run(method, room, P, seed, record=False):
    """Simulate one class. Returns (recorded frames or None, metrics dict)."""
    _, fn = METHODS[method]
    return fn(room, P, seed, method, record=record)
