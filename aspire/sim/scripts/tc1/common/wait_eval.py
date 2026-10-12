#!/usr/bin/env python3
"""Block until a detached eval (or any process) finishes, inside ONE tool call.

Claude Code agents must not end their turn to wait: a subagent that ends its turn is handed back
as finished. Call this from a Bash tool call with timeout 600000 ms and repeat while it exits 1.

  python3 scripts/tc1/common/wait_eval.py ITER_DIR          # evosearch_eval.py --iter-dir ITER_DIR
  python3 scripts/tc1/common/wait_eval.py --pid PID         # any detached process (replays, tests)

Exit codes:
  0  DONE     ITER_DIR/iter_summary.json exists (or PID has exited)
  1  RUNNING  still running after --max-wait seconds: call again
  3  DIED     no evosearch_eval.py process for ITER_DIR and no iter_summary.json: re-run the eval
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def _eval_running(iter_dir: Path) -> bool:
    target = iter_dir.resolve()
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = (proc / "cmdline").read_bytes().split(b"\0")
            cwd = Path(os.readlink(proc / "cwd"))
        except OSError:
            continue
        args = [a.decode(errors="replace") for a in args]
        if not any(a.endswith("evosearch_eval.py") for a in args) or "--iter-dir" not in args:
            continue
        i = args.index("--iter-dir")
        if i + 1 < len(args) and (cwd / args[i + 1]).resolve() == target:
            return True
    return False


def _trials(iter_dir: Path) -> int:
    return sum(1 for p in iter_dir.glob("candidate_*/eval/trial_*") if p.is_dir())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("iter_dir", nargs="?", type=Path)
    ap.add_argument("--pid", type=int)
    ap.add_argument("--max-wait", type=int, default=540, help="seconds (keep under the 600 s Bash limit)")
    ap.add_argument("--poll", type=int, default=20)
    a = ap.parse_args()
    if (a.iter_dir is None) == (a.pid is None):
        ap.error("give ITER_DIR or --pid")
    t0 = time.time()
    while True:
        if a.pid is not None:
            if not Path(f"/proc/{a.pid}").exists():
                print(f"DONE pid {a.pid} exited")
                return 0
            state = f"pid {a.pid} alive"
        else:
            if (a.iter_dir / "iter_summary.json").exists():
                print(f"DONE {a.iter_dir}/iter_summary.json ({_trials(a.iter_dir)} trial dirs)")
                return 0
            if not _eval_running(a.iter_dir):
                time.sleep(5)  # the summary may be written just after the process exits
                if (a.iter_dir / "iter_summary.json").exists():
                    continue
                print(f"DIED no evosearch_eval.py for {a.iter_dir} and no iter_summary.json "
                      f"({_trials(a.iter_dir)} trial dirs)")
                return 3
            state = f"{_trials(a.iter_dir)} trial dirs"
        if time.time() - t0 >= a.max_wait:
            print(f"RUNNING after {int(time.time() - t0)} s: {state} -- call again")
            return 1
        time.sleep(a.poll)


if __name__ == "__main__":
    sys.exit(main())
