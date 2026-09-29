#!/usr/bin/env python3
"""Results of one comparison run (evosearch rN, disagreement rN) in one screen.

Per round: best and mean dev pass rate, passes per candidate, dev seeds, next parents (selection.json).
Then the final pick (best.json) and the Stage 2 held-out manifest.

  # TC1, from aspire/sim
  .venv/bin/python3 scripts/tc1/summarize_run.py disagreement 1
  # laptop, on unpacked archives
  python3 summarize_run.py disagreement 1 --outputs <unpacked outputs/>

Standard library only.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

TASK = "libero_goal_swap/put_the_bowl_on_the_stove"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("arm", choices=["evosearch", "disagreement"])
    ap.add_argument("rep", type=int)
    ap.add_argument("--outputs", default="outputs")
    a = ap.parse_args()

    runs = sorted(glob.glob(f"{a.outputs}/claude_{a.arm}_r{a.rep}/{TASK}/2*/"))
    if not runs:
        sys.exit(f"no RUN_DIR under {a.outputs}/claude_{a.arm}_r{a.rep}/{TASK}")
    run = runs[-1]
    print("RUN_DIR", run)

    for d in sorted(glob.glob(run + "iter_*")):
        name = os.path.basename(d)
        f = f"{d}/iter_summary.json"
        if not os.path.isfile(f):
            print(f"{name}: no iter_summary.json")
            continue
        s = json.load(open(f))
        c = s["candidates"]
        passes = " ".join(f"{x['candidate'][-1]}{x['pass_count']}" for x in sorted(c, key=lambda x: x["candidate"]))
        mean = sum(x["pass_rate"] for x in c) / len(c)
        seeds = sorted({t["trial"] for x in c for t in x["trial_results"]})
        line = (f"{name}: best {s['best_candidate'][-1]} {s['best_pass_rate']:.0%}  mean {mean:.0%}  "
                f"passes {passes}  seeds {seeds[0]}-{seeds[-1]} ({len(seeds)})")
        sel = f"{d}/selection.json"
        if os.path.isfile(sel):
            j = json.load(open(sel))
            line += f"  -> next parents [{j['rule']}] " + ",".join(p.split("_")[-1] for p in j["parents"])
        print(line)

    if os.path.isfile(run + "best.json"):
        print("final pick (best.json):", json.load(open(run + "best.json"))["best"])
    else:
        print("no best.json (Stage 1 not finished?)")

    manifests = glob.glob(f"{a.outputs}/aspire_{a.arm}_eval_r{a.rep}/{TASK}/runs/*/manifest.json")
    if not manifests:
        print("no Stage 2 run")
    for m in manifests:
        j = json.load(open(m))
        print(f"Stage 2 {m.split('/runs/')[1].split('/')[0]}: {j.get('status')} "
              f"{j.get('passes')}/{j.get('trials')} ({j.get('pass_rate', 0):.0%})")


if __name__ == "__main__":
    main()
