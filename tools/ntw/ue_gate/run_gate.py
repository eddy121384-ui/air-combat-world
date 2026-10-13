"""Launch a runtime-gate stage in the ISOLATED UE5.8 project and sample the editor process memory from outside.

  python tools/ntw/ue_gate/run_gate.py build              # UnrealEditor-Cmd, builds /Game/NTWGate/L_NTWGate
  python tools/ntw/ue_gate/run_gate.py runtime --mode probe|full   # UnrealEditor.exe (real RHI, PIE)
Memory: psutil RSS / private bytes of the UnrealEditor process every 0.25 s -> <out>/memory.csv (wall clock, aligned offline
with the in-engine frame log). A hung editor is killed after --timeout seconds and the run is reported as such.
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
UE = Path(r"C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64")
ISO = Path(r"D:\Users\EDDY\UEIsolated")
PROJECT = ISO / "NTWRuntimeGate" / "NTWRuntimeGate.uproject"
OUT = ISO / "gate_out"
MAIN = Path(r"D:\Users\EDDY\Documents\GitHub\air-combat-world")   # read-only source of the accepted Xinyi contract


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["build", "runtime"])
    ap.add_argument("--mode", default="full", choices=["probe", "full", "followup"])
    ap.add_argument("--timeout", type=float, default=7200.0)
    a = ap.parse_args()
    env = dict(os.environ)
    if a.stage == "build":
        # a rebuilt level must not inherit World Partition external actors of a previous build (they would duplicate every actor)
        content = PROJECT.parent / "Content"
        for sub in ("NTWGate", "__ExternalActors__/NTWGate", "__ExternalObjects__/NTWGate"):
            d = content / sub
            if d.exists():
                shutil.rmtree(d)
                print("cleaned", d, flush=True)
        exe = UE / "UnrealEditor-Cmd.exe"
        script = HERE / "ue_gate_build.py"
        out = OUT
        env.update(ACW_GATE_TERRAIN_RUN=str(REPO / "data/generated/ntw/terrain/joint_ue_local"),
                   ACW_GATE_TERRAIN_RUN_V1=str(REPO / "data/generated/ntw/terrain/joint_ue_local_v1"),
                   ACW_GATE_XINYI_CONTRACT=str(MAIN / "unreal/Saved/XinyiUnrealV2Inputs/run-35822928983/unreal/Saved/XinyiUnrealV2Contract"),
                   ACW_GATE_AFFINE_JSON=str(OUT / "affine.json"), ACW_GATE_REPORT=str(OUT / "build.json"))
        log = OUT / "build.log"
    else:
        exe = UE / "UnrealEditor.exe"
        script = HERE / "ue_gate_runtime.py"
        out = OUT / ("runtime_" + a.mode)
        out.mkdir(parents=True, exist_ok=True)
        env.update(ACW_GATE_INPUTS=str(OUT / "gate_inputs.json"), ACW_GATE_OUT=str(out), ACW_GATE_MODE=a.mode)
        log = out / "runtime.log"
    cmd = [str(exe), str(PROJECT), "/Game/NTWGate/L_NTWGate", "-ExecutePythonScript=" + script.as_posix(), "-unattended", "-nopause",
           "-nosound", "-nosplash", "-abslog=" + log.as_posix()]
    print(" ".join(cmd), flush=True)
    t0 = time.time()
    p = subprocess.Popen(cmd, env=env)
    proc = psutil.Process(p.pid)
    rows = []
    timed_out = False
    while p.poll() is None:
        try:
            mi = proc.memory_info()
            rows.append([round(time.time(), 3), mi.rss, getattr(mi, "private", 0)])
        except psutil.Error:
            pass
        if time.time() - t0 > a.timeout:
            timed_out = True
            for c in proc.children(recursive=True):
                c.kill()
            p.kill()
            break
        time.sleep(0.25)
    with open(out / ("memory_%s.csv" % a.stage), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["wall", "rss_bytes", "private_bytes"])
        w.writerows(rows)
    print("exit", p.returncode, "timed_out", timed_out, "seconds", round(time.time() - t0, 1), flush=True)
    sys.exit(1 if timed_out else 0)


if __name__ == "__main__":
    main()
