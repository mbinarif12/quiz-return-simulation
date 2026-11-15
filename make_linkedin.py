"""Stitch the chart and chosen method videos into one LinkedIn video.

    python make_linkedin.py                               # default order below
    python make_linkedin.py --clips pile_desk one_stack   # choose clips

Layout: chart (intro) -> each method clip -> chart again (outro).
All parts are 1080 x 1350 at 30 fps; short fades join them.
"""
import argparse
import os
import subprocess

DEFAULT = ["pile_desk", "per_table", "one_stack"]   # same order as the cover: old way -> fastest -> my choice


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", nargs="+", default=DEFAULT)
    ap.add_argument("--chart", default="outputs/cover.png")
    ap.add_argument("--videos", default="outputs/videos_short")
    ap.add_argument("--intro", type=float, default=6.0)
    ap.add_argument("--outro", type=float, default=3.0)
    ap.add_argument("--out", default="outputs/linkedin_quiz_return.mp4")
    a = ap.parse_args()

    inputs, filters, labels = [], [], []
    fade = 0.3

    def still(sec, k):
        inputs.extend(["-loop", "1", "-framerate", "30", "-t", f"{sec}", "-i", a.chart])
        filters.append(f"[{k}:v]scale=1080:1350,fps=30,format=yuv420p,setsar=1,"
                       f"fade=t=in:st=0:d={fade},fade=t=out:st={sec - fade}:d={fade}[v{k}]")

    k = 0
    still(a.intro, k)
    labels.append(f"[v{k}]")
    for name in a.clips:
        k += 1
        path = os.path.join(a.videos, f"{name}.mp4")
        dur = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).strip())
        inputs.extend(["-i", path])
        filters.append(f"[{k}:v]scale=1080:1350,fps=30,format=yuv420p,setsar=1,"
                       f"fade=t=in:st=0:d={fade},fade=t=out:st={dur - fade}:d={fade}[v{k}]")
        labels.append(f"[v{k}]")
    k += 1
    still(a.outro, k)
    labels.append(f"[v{k}]")
    filters.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[out]")

    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters),
           "-map", "[out]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out]
    subprocess.run(cmd, check=True)
    dur = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", a.out]).strip().decode()
    print(a.out, f"{float(dur):.1f} s")


if __name__ == "__main__":
    main()
