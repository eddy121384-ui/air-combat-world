"""Parse the ProfileGPU dumps of a run_farlod_ab.ps1 -Profile run: per (view, cfg), the top-level passes (inclusive ms, draws, vertices)
of the frame profiled right after each SKYFL measurement. Prints the passes whose inclusive time differs most between two configs.
    python tools/skyfront/farlod_profile.py <run_dir> [cfg_a cfg_b] [depth=4]
Writes <run_dir>/report/profile.json.
"""
import json
import re
import sys
from pathlib import Path

ROW = re.compile(r"┃(.*?)┃(.*?)┃(\s*)(\S.*?)\s*┃\s*$")
MARK = re.compile(r"SKYFLPROFILE step=(\d+) view=(\S+) cfg=(\S+)")


def cells(s):
    p = [x.strip() for x in re.split(r"[│┊]", s)]
    return {"draws": int(p[0]), "prims": int(p[2]), "verts": int(p[3]), "ms": float(p[-1].split()[0])}


def main(run, a="high", b="high_fi", depth=4):
    run = Path(run)
    depth = int(depth)
    prof, cur, base = {}, None, None
    for ln in (run / "farlod.log").read_text(encoding="utf-8", errors="ignore").splitlines():
        m = MARK.search(ln)
        if m:
            cur = prof.setdefault(m.group(2), {}).setdefault(m.group(3), {"_n": 0})
            cur["_n"] += 1
            base = None
            continue
        if cur is None or "┃" not in ln:
            continue
        r = ROW.search(ln)
        if not r:
            continue
        try:
            inc = cells(r.group(2))
        except (ValueError, IndexError):
            continue
        ind = len(r.group(3))
        if base is None:
            base = ind
        lvl = (ind - base) // 3
        if lvl > depth:
            continue
        key = "%d:%s" % (lvl, re.sub(r"\d+x\d+", "WxH", r.group(4))[:60])
        e = cur.setdefault(key, {"ms": 0.0, "draws": 0, "verts": 0})
        e["ms"] += inc["ms"] / 1.0
        e["draws"] += inc["draws"]
        e["verts"] += inc["verts"]
    (run / "report").mkdir(exist_ok=True)
    (run / "report" / "profile.json").write_text(json.dumps(prof, indent=1) + "\n", encoding="utf-8")
    for view, cfgs in prof.items():
        if a not in cfgs or b not in cfgs:
            continue
        A, B = cfgs[a], cfgs[b]
        na, nb = A["_n"], B["_n"]
        rows = []
        for k in set(A) | set(B):
            if k == "_n":
                continue
            ea, eb = A.get(k, {"ms": 0, "draws": 0, "verts": 0}), B.get(k, {"ms": 0, "draws": 0, "verts": 0})
            rows.append((eb["ms"] / nb - ea["ms"] / na, k, ea["ms"] / na, eb["ms"] / nb, ea["draws"] // na, eb["draws"] // nb, ea["verts"] // na, eb["verts"] // nb))
        rows.sort(reverse=True)
        print("== %s: %s -> %s (profiles %d / %d)" % (view, a, b, na, nb))
        for d, k, ma, mb, da, db, va, vb in rows[:12]:
            print("  %+7.2f ms  %-62s %7.2f -> %7.2f  draws %5d -> %5d  verts %8d -> %8d" % (d, k, ma, mb, da, db, va, vb))


if __name__ == "__main__":
    main(*sys.argv[1:])
