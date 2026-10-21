"""Mobile forest profile: same-sequence-time frame pairs from two packaged -dumpmovie runs (run_packaged.ps1 -DumpMovie).

-dumpmovie writes one PNG per rendered frame in real time, so frame k's sequence time comes from the run's CSV (one row per frame):
cumulative FrameTime minus the load hitch (same rule as pk_analyze.py). For each requested sequence time the nearest frame of each run
is taken and the two are stacked side by side (left = first run, right = second run), with each frame's actual sequence time.
VALID FOR THE HELD STILLS ONLY: in the flight the two runs' frames at the same CSV time showed different places (the sequence clock of a
-dumpmovie run does not follow the CSV frame times closely enough at 1-3 fps); same-view flight frames come from MRQ instead.
    python tools/ntw/forest_world/movie_pairs.py <runs_dir> <frames_dir> <out_dir> runA runB t [t ...]
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

csv.field_size_limit(2**31 - 1)


def seq_times(p):
    rows = list(csv.reader(open(p, encoding="utf-8", errors="replace")))
    j = rows[0].index("FrameTime")
    end = next((i for i, r in enumerate(rows) if i > 0 and r and r[0] == "EVENTS"), len(rows))
    ft = np.array([float(r[j]) for r in rows[1:end]])
    t = np.cumsum(ft) / 1000.0
    k0 = int(np.argmax(np.where(t < 60, ft, -1)))
    return t - t[k0]


def main():
    runs_dir, frames_dir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    a, b = sys.argv[4], sys.argv[5]
    ts = [float(x) for x in sys.argv[6:]]
    out.mkdir(parents=True, exist_ok=True)
    meta = {}
    seq = {r: seq_times(runs_dir / r / "profile.csv") for r in (a, b)}
    for t in ts:
        picks = {}
        for r in (a, b):
            frames = sorted((frames_dir / r).glob("MovieFrame*.png"))
            s = seq[r][: len(frames)]
            k = int(np.argmin(np.abs(s - t)))
            picks[r] = (frames[k], round(float(s[k]), 2))
        name = "t%03ds" % round(t)
        for r, (f, _) in picks.items():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(f), "-q:v", "3", str(out / ("%s_%s.jpg" % (name, r)))], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(picks[a][0]), "-i", str(picks[b][0]), "-filter_complex",
                        "[0]scale=960:-1[x];[1]scale=960:-1[y];[x][y]hstack", "-q:v", "3", str(out / ("%s_pair.jpg" % name))], check=True)
        meta[name] = {r: {"frame": p[0].name, "sequence_time_s": p[1]} for r, p in picks.items()}
    (out / "pairs.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
