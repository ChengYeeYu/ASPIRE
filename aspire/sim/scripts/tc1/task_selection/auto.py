#!/usr/bin/env python3
"""Unattended driver for one task-selection arm: loops `tsel.py next` and runs each step itself.

Run inside auto_job.sh (perception servers already up), from aspire/sim:
  .venv/bin/python3 scripts/tc1/task_selection/auto.py --arm disagreement --deadline <epoch>
  .venv/bin/python3 scripts/tc1/task_selection/auto.py --arm disagreement --dry-run   # what it would run now

Every step is resumable, so a job killed at any point just continues in the next job:
  start / summarize / select / fix-begin / fix-end   run the tsel.py / libgen.py commands
  codegen, fix loop, disagreement selection           `claude -p` with the SAME prompt file as the
                                                      manual runs, plus a run-mode note (RUN_MODE)
  eval                                                libgen.py eval in the foreground
Claude steps run headless; a run that ends without advancing the step is retried (--max-attempts
per step per job), then the driver stops with an error.

Exit codes (auto_job.sh uses them): 0 arm done, 10 out of time (next job continues),
2 error or STOP file (chain stops).
Files: ROOT/<arm>/auto/auto.log (driver), auto/<time>_<step>.log (each claude/eval run),
auto/STOP (touch it to stop at the next step boundary), auto/FAILED (reason of the last error).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tsel  # noqa: E402
from tsel import HERE, LIBGEN, SNAP_SH, SIM, _fdir, _fixed, _load, _next, _phase, _rel, _snap  # noqa: E402

DONE, OUT_OF_TIME, ERROR = 0, 10, 2

# Appended to every prompt. Mechanics of the headless run only, nothing about the task.
RUN_MODE = """

==================================================================================================
RUN MODE (added by the unattended driver scripts/tc1/task_selection/auto.py)
==================================================================================================
This session runs headless (claude -p) inside a SLURM job. Nobody reads or answers anything you
write until the run is over. The session ends as soon as you end your turn, and anything you
started that is still running (subagents included) is killed. Therefore:
- Never end your turn while a subagent, eval or other process you started is still running.
- Run subagents in the FOREGROUND: Agent tool with run_in_background: false. To run several at
  once, put several Agent calls in one message.
- Where the instructions say STOP and report (or tell me), write the report as your final
  message and end. Do not ask questions.
- If the job's time runs out, the driver runs this same prompt again in the next job; the
  resume rules above apply.
"""

PHASE_RE = re.compile(r"^(?:(?P<arm>\w+)/)?round_(?P<n>\d+)(?: \(shared\))?: (?P<st>\w+)$")
FIX_RE = re.compile(r"^fix_(?P<n>\d+): (?P<what>select|begin|fix loop|end)")


class Stop(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


class Driver:
    def __init__(self, a):
        self.a, self.root, self.arm = a, a.root, a.arm
        self.adir = self.root / self.arm / "auto"
        self.attempts: dict[str, int] = {}

    # ── helpers ─────────────────────────────────────────────────────────────
    def log(self, msg: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        if not self.a.dry_run:
            with open(self.adir / "auto.log", "a") as f:
                f.write(line + "\n")

    def minutes_left(self) -> float:
        return (self.a.deadline - time.time()) / 60 if self.a.deadline else float("inf")

    def run(self, cmd: list[str], log: Path | None = None, check: bool = True) -> int:
        self.log("$ " + " ".join(cmd) + (f"   > {_rel(log)}" if log else ""))
        if self.a.dry_run:
            return 0
        if log:
            with open(log, "a") as f:
                rc = subprocess.run(cmd, cwd=SIM, stdout=f, stderr=subprocess.STDOUT).returncode
        else:
            rc = subprocess.run(cmd, cwd=SIM).returncode
        if check and rc != 0:
            raise Stop(ERROR, f"failed (rc={rc}): {' '.join(cmd)}")
        return rc

    def steplog(self, slug: str) -> Path:
        return self.adir / f"{time.strftime('%Y%m%d_%H%M%S')}_{re.sub(r'[^A-Za-z0-9]+', '_', slug).strip('_')}.log"

    def claude(self, prompt_file: str, subs: dict, slug: str) -> None:
        text = (SIM / prompt_file).read_text()
        for k, v in subs.items():
            text = text.replace("{{" + k + "}}", str(v))
        left = re.findall(r"\{\{[A-Z_]+\}\}", text)
        if left:
            raise Stop(ERROR, f"{prompt_file}: unfilled placeholders {sorted(set(left))}")
        cmd = ["claude", "-p", text + RUN_MODE, "--model", self.a.model, *self.a.claude_flags.split()]
        shown = ["claude", "-p", f"<{prompt_file} + RUN_MODE>", *cmd[3:]]
        log = self.steplog(slug)
        self.log("$ " + " ".join(shown) + f"   > {_rel(log)}")
        if self.a.dry_run:
            return
        with open(log, "a") as f:
            rc = subprocess.run(cmd, cwd=SIM, stdout=f, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL).returncode
        self.log(f"claude exited rc={rc}")

    # ── one step ────────────────────────────────────────────────────────────
    def step(self, step: str) -> None:
        py, root = ".venv/bin/python3", _rel(self.root)
        if step == "done":
            self.run([py, f"{HERE}/tsel.py", "report", "--arm", self.arm])
            raise Stop(DONE, f"arm {self.arm} done")

        m = PHASE_RE.match(step)
        if m:
            n, st = int(m["n"]), m["st"]
            if n == 0:
                raise Stop(ERROR, f"round_0 (shared) is '{st}': finish it by hand first (TASKSEL.md)")
            phase, snap = _phase(self.arm, n), _snap(self.arm, n)
            if st == "start":
                excl = _fixed(self.root, self.arm, n)
                self.run(["bash", SNAP_SH, "restore", snap])
                self.run([py, LIBGEN, "phase-start", "--root", root, "--phase", phase, "--snapshot", snap,
                          *(["--exclude", *excl] if excl else [])])
            elif st == "codegen":
                self.run([py, LIBGEN, "status", "--root", root, "--phase", phase])  # exits 1 if library changed
                self.claude("scripts/tc1/library_gain/libgen_codegen_prompt.md",
                            {"ROOT": root, "PHASE": phase}, f"codegen_{phase}")
            elif st == "eval":
                self.run([".venv-libero/bin/python3", LIBGEN, "eval", "--root", root, "--phase", phase],
                         log=self.root / phase / "eval_driver.log", check=False)
            elif st == "summarize":
                self.run([py, LIBGEN, "summarize", "--root", root, "--phase", phase])
                self.run(["bash", SNAP_SH, "check", snap])
            else:
                raise Stop(ERROR, f"unknown phase state {st!r}")
            return

        m = FIX_RE.match(step)
        if not m:
            raise Stop(ERROR, f"cannot handle step {step!r} (init/probe/empty library: do them by hand)")
        n, what, fdir = int(m["n"]), m["what"], _fdir(self.root, self.arm, int(m["n"]))
        nn = ["--arm", self.arm, "--n", str(n)]
        if what == "select":
            self.run([py, f"{HERE}/tsel.py", "select", *nn])  # top_down: writes select.json
            if self.arm == "disagreement" and not (fdir / "select.json").exists():
                self.claude(f"{HERE}/select_disagreement_prompt.md",
                            {"INPUT": _rel(fdir / "select_input.json"), "OUT": _rel(fdir / "select.json"),
                             "ROUND": n}, f"select_{n}")
                if (fdir / "select.json").exists():
                    self.run([py, f"{HERE}/tsel.py", "select", *nn])  # validates; exits 1 if invalid
        elif what == "begin":
            self.run([py, f"{HERE}/tsel.py", "fix-begin", *nn])
        elif what == "fix loop":
            fx = _load(fdir / "fix.json")
            self.claude(f"{HERE}/fix_prompt.md",
                        {"ARM": fx["arm"], "N": fx["round"], "SUITE": fx["suite"], "TASK": fx["task"],
                         "FROM": fx["from_snapshot"], "TO": fx["to_snapshot"]}, f"fix_{n}")
        elif what == "end":
            self.run([py, f"{HERE}/tsel.py", "fix-end", *nn])

    # ── main loop ───────────────────────────────────────────────────────────
    def loop(self) -> int:
        if not self.a.dry_run:
            self.adir.mkdir(parents=True, exist_ok=True)
        other = [x for x in tsel.ARMS if x != self.arm]
        for o in other:
            st = _next(self.root, o)[0]
            if st != "done" and not self.a.ignore_other_arm:
                raise Stop(ERROR, f"arm {o} is not done ({st}); the arms share .claude/libero/skills/, "
                                  f"finish it first (or --ignore-other-arm)")
        self.log(f"driver start: arm {self.arm}, model {self.a.model}, flags '{self.a.claude_flags}', "
                 f"{self.minutes_left():.0f} min left")
        while True:
            if (self.adir / "STOP").exists():
                raise Stop(ERROR, f"STOP file {_rel(self.adir / 'STOP')} present")
            step = _next(self.root, self.arm)[0]
            self.log(f"next: {step}")
            if self.a.dry_run:
                self.step(step)
                return DONE
            if self.minutes_left() < self.a.min_left:
                raise Stop(OUT_OF_TIME, f"{self.minutes_left():.0f} min left (< {self.a.min_left}): "
                                        f"leaving '{step}' to the next job")
            self.attempts[step] = self.attempts.get(step, 0) + 1
            if self.attempts[step] > self.a.max_attempts:
                raise Stop(ERROR, f"'{step}' did not advance after {self.a.max_attempts} attempts in this job; "
                                  f"see the latest logs in {_rel(self.adir)}")
            self.step(step)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=SIM / "outputs/task_selection")
    ap.add_argument("--arm", choices=tsel.ARMS, default="disagreement")
    ap.add_argument("--deadline", type=float, default=0, help="epoch seconds when the job ends (0 = none)")
    ap.add_argument("--min-left", type=float, default=20, help="minutes; start no step with less left")
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--claude-flags", default="--permission-mode auto")
    ap.add_argument("--ignore-other-arm", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print the current step's commands, run nothing")
    a = ap.parse_args()
    a.root = a.root if a.root.is_absolute() else (Path.cwd() / a.root)
    d = Driver(a)
    try:
        return d.loop()
    except Stop as s:
        d.log(("STOPPED: " if s.code else "") + str(s))
        if s.code == ERROR and not a.dry_run:
            d.adir.mkdir(parents=True, exist_ok=True)
            (d.adir / "FAILED").write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {s}\n")
        return s.code


if __name__ == "__main__":
    sys.exit(main())
