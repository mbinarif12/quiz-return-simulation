"""One video per method: both rooms stacked, one shared clock.

Output is 1080 x 1350 (4:5 portrait), which plays well in a phone feed.
"""
from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager as _fm  # noqa: E402

for _f in _fm.findSystemFonts():         # use Inter when it is installed
    if "Inter" in _f:
        _fm.fontManager.addfont(_f)
plt.rcParams["font.family"] = ["Inter", "DejaVu Sans"]
import numpy as np  # noqa: E402
from matplotlib.animation import FFMpegWriter  # noqa: E402
from matplotlib.patches import Circle, Rectangle  # noqa: E402

from .common import CARRYING, GONE, GOT, MISSED, SEARCHING, WAITING  # noqa: E402

# Dark theme, colours from a colour-blind-checked categorical palette (dark steps)
# Light theme; state colours are the light steps of a colour-blind-checked palette
BG = "#FAF8F3"
SURFACE = "#ffffff"
INK = "#161616"
INK2 = "#6E6B66"
MUTED = "#8a8984"
WALL = "#6b6a65"
FURN = "#ebe9e3"
FURN_EDGE = "#c9c7bf"
COL = {WAITING: "#a8a69f", SEARCHING: "#eb6834", GOT: "#1baf7a",
       CARRYING: "#2a78d6", MISSED: "#e34948"}
TEACHER = "#6250d6"
STACK = "#1d1d1b"
DONE = "#0f7a52"
LABELS = [(WAITING, "Waiting"), (SEARCHING, "Searching"), (GOT, "Has quiz"),
          (CARRYING, "Walking with stack"), (MISSED, "No quiz")]


def _fmt(sec):
    sec = max(0, int(round(sec)))
    return f"{sec // 60:d}:{sec % 60:02d}"


def draw_room(ax, room):
    W, D = room.width, room.depth
    ax.set_facecolor(SURFACE)
    ax.set_xlim(-0.5, W + 0.5)
    ax.set_ylim(-0.9, D + 0.3)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), W, D, facecolor=SURFACE, edgecolor="none", zorder=0))

    # walls with door gaps
    walls = {"front": [(0, W)], "back": [(0, W)], "left": [(0, D)], "right": [(0, D)]}
    for d in room.shapes["doors"]:
        segs = []
        for a, b in walls[d["wall"]]:
            if d["from"] > a:
                segs.append((a, d["from"]))
            if d["to"] < b:
                segs.append((d["to"], b))
        walls[d["wall"]] = segs
    for wall, segs in walls.items():
        for a, b in segs:
            if wall == "front":
                ax.plot([a, b], [0, 0], color=WALL, lw=3, solid_capstyle="butt")
            elif wall == "back":
                ax.plot([a, b], [D, D], color=WALL, lw=3, solid_capstyle="butt")
            elif wall == "left":
                ax.plot([0, 0], [a, b], color=WALL, lw=3, solid_capstyle="butt")
            else:
                ax.plot([W, W], [a, b], color=WALL, lw=3, solid_capstyle="butt")
    for d in room.shapes["doors"]:
        mid = (d["from"] + d["to"]) / 2
        if d["wall"] == "front":
            ax.text(mid, -0.45, "door", color=INK2, ha="center", va="center", fontsize=11)
        elif d["wall"] == "left":
            ax.text(-0.25, mid, "door", color=INK2, ha="center", va="center", fontsize=11, rotation=90)

    for dec in room.shapes["decor"]:
        lab = "whiteboard" if dec["kind"] == "whiteboard" else "screen"
        c = "#b9b7af" if dec["kind"] == "whiteboard" else "#9c94e0"
        a, b = dec["from"], dec["to"]
        if dec["wall"] == "front":
            ax.plot([a, b], [0.08, 0.08], color=c, lw=4, solid_capstyle="butt")
            ax.text((a + b) / 2, -0.45, lab, color=MUTED, ha="center", va="center", fontsize=10)
        elif dec["wall"] in ("left", "right"):
            x = 0.08 if dec["wall"] == "left" else W - 0.08
            ax.plot([x, x], [a, b], color=c, lw=4, solid_capstyle="butt")

    for cx, cy, r in room.shapes["circles"]:
        ax.add_patch(Circle((cx, cy), r, facecolor=FURN, edgecolor=FURN_EDGE, lw=1.2, zorder=1))
    for x, y, w, h, kind in room.shapes["rects"]:
        if kind == "desk":
            ax.add_patch(Rectangle((x, y), w, h, facecolor="#ecebfa", edgecolor=TEACHER, lw=1.2, zorder=1))
            ax.text(x + w / 2, y + h / 2, "desk", color=INK2, ha="center", va="center", fontsize=10, zorder=2)
        else:
            ax.add_patch(Rectangle((x, y), w, h, facecolor=FURN, edgecolor=FURN_EDGE, lw=1.0, zorder=1))
    sx = [room.centre(s)[0] for s in room.seats]
    sy = [room.centre(s)[1] for s in room.seats]
    ax.scatter(sx, sy, s=34, facecolors="none", edgecolors="#d6d4cc", lw=0.8, zorder=2)



FIG_W, FIG_H = 10.8, 13.5
LM = 72 / 1080          # left/right margin, same as the cover image


class RoomPanel:
    """One room: the floor plan, people, stacks, and a one-line status."""

    def __init__(self, fig, rect, room, sim, metrics, method):
        self.room, self.sim, self.m, self.method = room, sim, metrics, method
        self.ax = fig.add_axes(rect)
        draw_room(self.ax, room)
        x0, y0, w, h = rect
        fig.text(x0, y0 + h + 0.008, room.short_name, color=INK, fontsize=17, fontweight="bold",
                 ha="left", va="bottom")
        self.status = fig.text(x0 + w, y0 + h + 0.008, "", color=INK2, fontsize=15, ha="right",
                               va="bottom")
        n = sim["xy"].shape[1]
        self.dots = self.ax.scatter(np.zeros(n), np.zeros(n), s=95, c=[COL[WAITING]] * n,
                                    edgecolors=SURFACE, linewidths=1.0, zorder=5)
        self.teacher = self.ax.scatter([0], [0], s=280, marker="*", c=TEACHER, edgecolors=SURFACE,
                                       linewidths=1.0, zorder=6)
        S = sim["stack_n"].shape[1]
        self.stacks = self.ax.scatter(np.zeros(S), np.zeros(S), s=120, marker="s", c=STACK,
                                      edgecolors=SURFACE, linewidths=1.0, zorder=7)
        self.labels = [self.ax.text(0, 0, "", color=INK, fontsize=12, fontweight="bold", ha="center",
                                    va="bottom", zorder=8) for _ in range(S)]
        self.T = len(sim["t"])

    def update(self, t_sim, window, dt):
        sim = self.sim
        k = min(int(round(t_sim / dt)), self.T - 1)
        done = k >= self.T - 1
        lo = k if done else max(0, k - window + 1)
        with np.errstate(all="ignore"), _quiet():
            xy = np.nanmean(sim["xy"][lo:k + 1], axis=0)
            sxy = np.nanmean(sim["stack_xy"][lo:k + 1], axis=0)
        st = sim["state"][k]
        show = (st != GONE)[:, None]
        self.dots.set_offsets(np.where(show, xy, np.nan))
        self.dots.set_facecolors([COL.get(int(s), COL[WAITING]) for s in st])
        self.teacher.set_offsets([sim["teacher"][lo:k + 1].mean(axis=0)])
        n = sim["stack_n"][k]
        off = np.array([0.0, 0.0]) if self.method.startswith("pile") else np.array([0.26, 0.26])
        pts = []
        for j, lab in enumerate(self.labels):
            p = sxy[j] + off
            if np.isnan(p[0]) or (n[j] == 0 and not self.method.startswith("pile")):
                pts.append((np.nan, np.nan))
                lab.set_text("")
                continue
            pts.append(p)
            lab.set_position((p[0], p[1] + 0.28))
            lab.set_text(str(int(n[j])))
        self.stacks.set_offsets(pts)

        ret = int(sim["returned"][k])
        N = self.m["n_present"]
        if self.method.startswith("pile"):
            extra = "after class"
        else:
            lost = self.m["teaching_lost_s"] if done else min(t_sim, self.m["teaching_lost_s"])
            extra = f"{_fmt(lost)} teaching lost"
        if done:
            self.status.set_text(f"done {_fmt(sim['t'][-1])} · {ret}/{N} returned · {extra}")
            self.status.set_color(DONE)
        else:
            self.status.set_text(f"{ret:2d}/{N} returned · {extra}")


class _quiet:
    def __enter__(self):
        import warnings
        self._w = warnings.catch_warnings()
        self._w.__enter__()
        warnings.simplefilter("ignore")

    def __exit__(self, *a):
        self._w.__exit__(*a)


def _build(rooms, sims, metrics, method, title, subtitle, end_text, target_seconds):
    t_end = max(s["t"][-1] for s in sims)
    speed = max(1, int(math.ceil(t_end / target_seconds / 5.0)) * 5)
    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=100, facecolor=BG)
    fig.text(LM, 0.965, title, color=INK, fontsize=34, fontweight="bold", va="top",
             fontfamily="Inter Display")
    fig.text(LM, 0.918, subtitle, color=INK2, fontsize=17, va="top", linespacing=1.35)
    clock = fig.text(1 - LM, 0.965, "0:00", color=INK, fontsize=34, fontweight="bold", ha="right",
                     va="top", fontfamily="Inter Display")
    fig.text(1 - LM, 0.918, f"{speed}× speed", color=INK2, fontsize=15, ha="right", va="top")

    panels = []
    tops = [0.838, 0.455]
    max_h = 0.33
    for room, sim, m, top in zip(rooms, sims, metrics, tops):
        W, D = room.width + 1.0, room.depth + 1.2
        h = max_h
        w = h * (FIG_H / FIG_W) * W / D
        if w > 0.9:
            w = 0.9
            h = w / ((FIG_H / FIG_W) * W / D)
        panels.append(RoomPanel(fig, [0.5 - w / 2, top - h - 0.025, w, h], room, sim, m, method))

    search_label = "Being called" if method == "calling" else "Searching"
    items = [("●", COL[code], search_label if code == SEARCHING else lab) for code, lab in LABELS
             if not ((method == "calling" or method.startswith("pile")) and code == CARRYING)]
    items += [("★", TEACHER, "Me"), ("■", STACK, "Quizzes (number = sheets left)")]
    legend = []
    renderer = fig.canvas.get_renderer()
    rows = [items[:len(items) - 2], items[len(items) - 2:]]
    for row, y in zip(rows, (0.068, 0.033)):
        lx = LM
        for sym, col, lab in row:
            a = fig.text(lx, y, sym, color=col, fontsize=17, va="center")
            b = fig.text(lx + 0.026, y, lab, color=INK2, fontsize=15, va="center")
            legend += [a, b]
            w = b.get_window_extent(renderer).width / fig.bbox.width
            lx += 0.026 + w + 0.035
    end = fig.text(LM, 0.075, end_text, color=INK, fontsize=16, ha="left", va="center",
                   linespacing=1.5)
    end.set_visible(False)
    end.legend = legend
    return fig, clock, panels, end, speed, t_end


def _show_end(end, on):
    end.set_visible(on)
    for a in end.legend:
        a.set_visible(not on)


def render_method(rooms, sims, metrics, method, title, subtitle, end_text, out_path,
                  dt=0.1, fps=30, target_seconds=35, hold_seconds=5):
    fig, clock, panels, end, speed, t_end = _build(rooms, sims, metrics, method, title, subtitle,
                                                   end_text, target_seconds)
    n_frames = int(t_end / speed * fps) + 2 + int(hold_seconds * fps)
    window = max(1, int(round(speed / fps / dt)))
    writer = FFMpegWriter(fps=fps, codec="libx264",
                          extra_args=["-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20"])
    with writer.saving(fig, out_path, dpi=100):
        for f in range(n_frames):
            t_sim = min(f * speed / fps, t_end)
            clock.set_text(_fmt(t_sim))
            for p in panels:
                p.update(t_sim, window, dt)
            _show_end(end, t_sim >= t_end)
            writer.grab_frame(facecolor=BG)
    plt.close(fig)
    return dict(speed=speed, frames=n_frames, seconds=round(n_frames / fps, 1))


def render_still(rooms, sims, metrics, method, title, subtitle, end_text, t_sim, out_png,
                 dt=0.1, fps=30, target_seconds=35):
    fig, clock, panels, end, speed, t_end = _build(rooms, sims, metrics, method, title, subtitle,
                                                   end_text, target_seconds)
    window = max(1, int(round(speed / fps / dt)))
    t_sim = min(t_sim, t_end)
    clock.set_text(_fmt(t_sim))
    for p in panels:
        p.update(t_sim, window, dt)
    _show_end(end, t_sim >= t_end)
    fig.savefig(out_png, facecolor=BG, dpi=100)
    plt.close(fig)
    return out_png
