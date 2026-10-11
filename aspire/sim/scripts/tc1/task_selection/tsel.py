#!/usr/bin/env python3
"""Task selection for building a skill library: disagreement vs top-to-bottom (original ASPIRE).

Each arm starts from an EMPTY skill library (snapshot TS_L0_empty) and runs ROUNDS rounds:
  round_0 (shared by both arms): K=3 zero-shot programs per task from L0, eval on seeds 51-65
  for n = 1..ROUNDS:
    select   one not-yet-fixed task from the previous round's results, by the arm's rule
               top_down:     first unfixed task in manifest order (ASPIRE works down its task table)
               disagreement: an agent reads the previous round's results (select_disagreement_prompt.md)
    fix      fix loop on that task, starting from its best program of the previous round,
             <= 5 iterations on 51-65, skills promoted -> library L_n (snapshot TS_L<n>_<arm>)
    round_n  K fresh programs from L_n for every task not fixed yet, eval on 51-65

Layout (ROOT = outputs/task_selection):
  ROOT/manifest.json, ROOT/probe/                     libgen.py init / probe (shared)
  ROOT/round_0/                                       libgen phase, shared by both arms
  ROOT/<arm>/fix_<n>/select_input.json, select.json   selection
  ROOT/<arm>/fix_<n>/fix.json                         fix-begin: task, start program, parked dirs
  ROOT/<arm>/fix_<n>/libero_fix_loop*/ working_codes/ moved here by fix-end
  ROOT/<arm>/round_<n>/                               libgen phase "<arm>/round_<n>"
  ROOT/<arm>/report.json                              report

  .venv/bin/python3 scripts/tc1/task_selection/tsel.py next --arm disagreement   # what to run now
  .venv/bin/python3 scripts/tc1/task_selection/tsel.py init                       # manifest (9 tasks, K=3, 51-65)
  .venv/bin/python3 scripts/tc1/task_selection/tsel.py select    --arm A --n N
  .venv/bin/python3 scripts/tc1/task_selection/tsel.py fix-begin --arm A --n N
  .venv/bin/python3 scripts/tc1/task_selection/tsel.py fix-end   --arm A --n N
  .venv/bin/python3 scripts/tc1/task_selection/tsel.py report    [--arm A ...]
Run from aspire/sim. One arm at a time: both arms share the skill-library working tree.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "library_gain"))
import libgen  # noqa: E402
from libgen import SIM, SNAPSHOTS, _candidates, _load, _split, _write  # noqa: E402

ROUNDS = 3
K = 3
SEEDS = "51-65"
ARMS = ("disagreement", "top_down")
# Manifest order = top-to-bottom order.
TASKS = [
    "libero_goal_swap/open_the_middle_drawer_of_the_cabinet",
    "libero_goal_swap/put_the_bowl_on_the_stove",
    "libero_goal_swap/turn_on_the_stove",
    "libero_spatial_swap/pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate",
    "libero_spatial_swap/pick_up_the_black_bowl_next_to_the_ramekin_and_place_it_on_the_plate",
    "libero_spatial_swap/pick_up_the_black_bowl_from_table_center_and_place_it_on_the_plate",
    "libero_object_swap/pick_up_the_alphabet_soup_and_place_it_in_the_basket",
    "libero_object_swap/pick_up_the_cream_cheese_and_place_it_in_the_basket",
    "libero_object_swap/pick_up_the_salad_dressing_and_place_it_in_the_basket",
]
HERE = "scripts/tc1/task_selection"
LIBGEN = "scripts/tc1/library_gain/libgen.py"
SNAP_SH = "scripts/tc1/common/skills_snapshot.sh"
FIX_DIRS = ("libero_fix_loop", "libero_fix_loop_debug", "working_codes")


def _rel(p: Path) -> str:
    return os.path.relpath(p, SIM)


def _snap(arm: str, n: int) -> str:
    return "TS_L0_empty" if n == 0 else f"TS_L{n}_{arm}"


def _phase(arm: str, n: int) -> str:
    return "round_0" if n == 0 else f"{arm}/round_{n}"


def _fdir(root: Path, arm: str, n: int) -> Path:
    return root / arm / f"fix_{n}"


def _fixed(root: Path, arm: str, upto: int) -> list[str]:
    """Tasks chosen for fix loops 1..upto (only those whose select.json exists)."""
    out = []
    for k in range(1, upto + 1):
        p = _fdir(root, arm, k) / "select.json"
        if p.exists():
            out.append(_load(p)["chosen_task"])
    return out


def _unfixed(root: Path, arm: str, n: int) -> list[str]:
    """Tasks a fix loop at step n may choose from, in manifest order."""
    done = set(_fixed(root, arm, n - 1))
    return [t for t in libgen._manifest(root)["tasks"] if t not in done]


def _check_select(root: Path, arm: str, n: int) -> str:
    p = _fdir(root, arm, n) / "select.json"
    if not p.exists():
        sys.exit(f"no {_rel(p)} -- run select first")
    s = _load(p)
    if s.get("arm") != arm or s.get("round") != n:
        sys.exit(f"{_rel(p)}: arm/round {s.get('arm')}/{s.get('round')} != {arm}/{n}")
    if s.get("chosen_task") not in _unfixed(root, arm, n):
        sys.exit(f"{_rel(p)}: chosen_task {s.get('chosen_task')!r} is not an unfixed task of this arm")
    return s["chosen_task"]


def _phase_state(root: Path, phase: str) -> str:
    pdir = root / phase
    if not (pdir / "phase.json").exists():
        return "start"
    ph = _load(pdir / "phase.json")
    cands = _candidates(libgen._manifest(root)["k"])
    for t in ph["tasks"]:
        for c in cands:
            f = pdir / t / c / "code.py"
            if not f.exists() or f.stat().st_size == 0:
                return "codegen"
    if any(not (pdir / t / "iter_summary.json").exists() for t in ph["tasks"]):
        return "eval"
    return "summarize" if not (pdir / "summary.json").exists() else "done"


def _sh(cmd: list[str]) -> None:
    r = subprocess.run(cmd, cwd=SIM)
    if r.returncode != 0:
        sys.exit(f"failed: {' '.join(cmd)}")


# ── init ────────────────────────────────────────────────────────────────────

def cmd_init(a) -> None:
    _sh([str(libgen.LIBERO_PY), LIBGEN, "init", "--root", str(a.root), "--tasks", *TASKS,
         "--max-tasks", str(len(TASKS)), "--k", str(K), "--seeds", SEEDS])


# ── next: print the next step for one arm ───────────────────────────────────

def _phase_cmds(root: Path, phase: str, snap: str, exclude: list[str]) -> list[str]:
    r, st = _rel(root), _phase_state(root, phase)
    if st == "start":
        excl = (" --exclude " + " ".join(exclude)) if exclude else ""
        return [f"bash {SNAP_SH} restore {snap}",
                f".venv/bin/python3 {LIBGEN} phase-start --root {r} --phase {phase} --snapshot {snap}{excl}"]
    if st == "codegen":
        return [f".venv/bin/python3 {LIBGEN} status --root {r} --phase {phase}   # library must be OK",
                f'claude "$(sed -e "s|{{{{ROOT}}}}|{r}|g" -e "s|{{{{PHASE}}}}|{phase}|g" '
                f'scripts/tc1/library_gain/libgen_codegen_prompt.md)"']
    if st == "eval":
        return [f"setsid nohup .venv-libero/bin/python3 {LIBGEN} eval --root {r} --phase {phase} "
                f"> {r}/{phase}/eval_driver.log 2>&1 &",
                f"tail -f {r}/{phase}/eval_driver.log"]
    if st == "summarize":
        return [f".venv/bin/python3 {LIBGEN} summarize --root {r} --phase {phase}",
                f"bash {SNAP_SH} check {snap}   # nothing touched the library"]
    return []


def _fix_cmd(fx: dict) -> str:
    subs = {"ARM": fx["arm"], "N": fx["round"], "SUITE": fx["suite"], "TASK": fx["task"],
            "FROM": fx["from_snapshot"], "TO": fx["to_snapshot"]}
    sed = " ".join(f'-e "s|{{{{{k}}}}}|{v}|g"' for k, v in subs.items())
    return f'claude "$(sed {sed} {HERE}/fix_prompt.md)"'


def _next(root: Path, arm: str) -> tuple[str, list[str]]:
    r = _rel(root)
    if not (root / "manifest.json").exists():
        return "init", [f".venv/bin/python3 {HERE}/tsel.py init"]
    m = libgen._manifest(root)
    if any(not (root / "probe" / f"{t}.txt").exists()
           or "PROBE_DONE" not in (root / "probe" / f"{t}.txt").read_text() for t in m["tasks"]):
        return "probe", [f".venv-libero/bin/python3 {LIBGEN} probe --root {r}   # resumable"]
    if not (SNAPSHOTS / _snap(arm, 0) / "SHA256SUMS").exists():
        return "empty library", [f"bash {SNAP_SH} save-empty {_snap(arm, 0)}"]
    st = _phase_state(root, "round_0")
    if st != "done":
        return f"round_0 (shared): {st}", _phase_cmds(root, "round_0", _snap(arm, 0), [])
    for n in range(1, ROUNDS + 1):
        fdir = _fdir(root, arm, n)
        if not (fdir / "select.json").exists():
            return f"fix_{n}: select", [f".venv/bin/python3 {HERE}/tsel.py select --arm {arm} --n {n}"]
        if not (fdir / "fix.json").exists():
            return f"fix_{n}: begin", [f".venv/bin/python3 {HERE}/tsel.py fix-begin --arm {arm} --n {n}"]
        fx = _load(fdir / "fix.json")
        if "ended" not in fx:
            if not (SNAPSHOTS / fx["to_snapshot"] / "SHA256SUMS").exists():
                return f"fix_{n}: fix loop on {fx['suite']}/{fx['task']} (resume = same command)", [_fix_cmd(fx)]
            return f"fix_{n}: end", [f".venv/bin/python3 {HERE}/tsel.py fix-end --arm {arm} --n {n}"]
        phase = _phase(arm, n)
        st = _phase_state(root, phase)
        if st != "done":
            return f"{phase}: {st}", _phase_cmds(root, phase, _snap(arm, n), _fixed(root, arm, n))
    return "done", [f".venv/bin/python3 {HERE}/tsel.py report --arm {arm}"]


def cmd_next(a) -> None:
    step, cmds = _next(a.root, a.arm)
    print(f"arm {a.arm} -- next: {step}")
    for c in cmds:
        print(f"  {c}")
    other = [x for x in ARMS if x != a.arm]
    print(f"(never run {', '.join(other)} at the same time: the arms share .claude/libero/skills/)")


# ── select ──────────────────────────────────────────────────────────────────

def cmd_select(a) -> None:
    root, arm, n = a.root, a.arm, a.n
    prev = _phase(arm, n - 1)
    if _phase_state(root, prev) != "done":
        sys.exit(f"phase {prev} not finished")
    for k in range(1, n):
        if "ended" not in _load(_fdir(root, arm, k) / "fix.json"):
            sys.exit(f"fix_{k} not ended")
    fdir = _fdir(root, arm, n)
    if (fdir / "select.json").exists():
        print(f"{_rel(fdir / 'select.json')} exists: {_check_select(root, arm, n)}")
        return
    unfixed = _unfixed(root, arm, n)
    summary = _load(root / prev / "summary.json")
    if sorted(summary["tasks"]) != sorted(unfixed):
        sys.exit(f"{prev}/summary.json tasks != unfixed tasks of {arm} at step {n}")
    fdir.mkdir(parents=True, exist_ok=True)
    if arm == "top_down":
        _write(fdir / "select.json", {
            "arm": arm, "round": n, "from_phase": prev, "rule": "first unfixed task in manifest order",
            "chosen_task": unfixed[0], "unfixed": unfixed, "chosen": time.strftime("%Y-%m-%d %H:%M:%S")})
        print(f"top_down step {n}: {unfixed[0]}")
        return
    inp = fdir / "select_input.json"
    _write(inp, {"arm": arm, "round": n, "from_phase": prev, "seeds": summary["seeds"], "k": summary["k"],
                 "programs_dir": _rel(root / prev), "tasks": {t: summary["tasks"][t] for t in unfixed}})
    print(f"wrote {_rel(inp)}; now run the selection agent (it writes {_rel(fdir / 'select.json')}):")
    print(f'  claude "$(sed -e "s|{{{{INPUT}}}}|{_rel(inp)}|g" -e "s|{{{{OUT}}}}|{_rel(fdir / "select.json")}|g" '
          f'-e "s|{{{{ROUND}}}}|{n}|g" {HERE}/select_disagreement_prompt.md)"')
    print(f"  .venv/bin/python3 {HERE}/tsel.py select --arm {arm} --n {n}   # validates the choice")


# ── fix-begin / fix-end ─────────────────────────────────────────────────────

def _passes(c: dict) -> int:
    return sum(r["task_completed"] for r in c["trial_results"])


def cmd_fix_begin(a) -> None:
    root, arm, n = a.root, a.arm, a.n
    tid = _check_select(root, arm, n)
    fdir = _fdir(root, arm, n)
    if (fdir / "fix.json").exists():
        sys.exit(f"{_rel(fdir / 'fix.json')} exists -- resume with:\n  {_fix_cmd(_load(fdir / 'fix.json'))}")
    suite, task = _split(tid)
    frm, to = _snap(arm, n - 1), _snap(arm, n)
    if (SNAPSHOTS / to).exists():
        sys.exit(f"snapshot {to} already exists")
    prev = root / _phase(arm, n - 1) / tid
    summ = _load(prev / "iter_summary.json")
    best = min(summ["candidates"], key=lambda c: (-_passes(c), c["errors"], c["candidate"]))

    _sh(["bash", SNAP_SH, "restore", frm])
    out = SIM / "outputs"
    parked = None
    if any((out / d).exists() for d in FIX_DIRS):
        parked = out / f"parked_{time.strftime('%Y%m%d_%H%M%S')}"
        parked.mkdir()
        for d in FIX_DIRS:
            if (out / d).exists():
                (out / d).rename(parked / d)
        print(f"parked {[d for d in FIX_DIRS if (parked / d).exists()]} -> {_rel(parked)}")

    tdir = out / "libero_fix_loop" / suite / task
    it0 = tdir / "iters" / "iter_0"
    shutil.copytree(prev / best["candidate"], it0 / "candidate_A", ignore=shutil.ignore_patterns("eval_partial_*"))
    shutil.copy(prev / best["candidate"] / "code.py", tdir / "start_code.py")
    src = f"{_phase(arm, n - 1)}/{tid}/{best['candidate']}"
    _write(it0 / "iter_summary.json", {
        **{k: v for k, v in summ.items() if k not in ("candidates", "best_candidate", "best_pass_rate")},
        "candidates": [{**best, "candidate": "candidate_A", "copied_from": src}],
        "best_candidate": "candidate_A", "best_pass_rate": best["pass_rate"]})
    fx = {"arm": arm, "round": n, "suite": suite, "task": task, "start_program": src,
          "start_passes": _passes(best), "trials": len(best["trial_results"]),
          "from_snapshot": frm, "to_snapshot": to, "parked": _rel(parked) if parked else None,
          "begun": time.strftime("%Y-%m-%d %H:%M:%S")}
    _write(fdir / "fix.json", fx)
    print(f"fix_{n} ({arm}): {tid}, start = {src} ({fx['start_passes']}/{fx['trials']}), library {frm}")
    print(f"  {_fix_cmd(fx)}")


def cmd_fix_end(a) -> None:
    root, arm, n = a.root, a.arm, a.n
    fdir = _fdir(root, arm, n)
    fx = _load(fdir / "fix.json")
    if "ended" in fx:
        sys.exit(f"fix_{n} already ended")
    out = SIM / "outputs"
    tdir = out / "libero_fix_loop" / fx["suite"] / fx["task"]
    for f in ("fix_code.py", "findings.md"):
        if not (tdir / f).exists():
            sys.exit(f"missing {_rel(tdir / f)} -- fix loop not finished")
    _sh([".venv/bin/python3", "scripts/libero/record_skill_promotion.py", "verify",
         "--suite", fx["suite"], "--task", fx["task"]])
    _sh(["bash", SNAP_SH, "check", fx["to_snapshot"]])

    fix_sha = hashlib.sha256((tdir / "fix_code.py").read_bytes()).hexdigest()
    iters = []
    for d in sorted((tdir / "iters").glob("iter_*"), key=lambda p: int(p.name.split("_")[1])):
        if (d / "iter_summary.json").exists():
            c = _load(d / "iter_summary.json")["candidates"][0]
            code = d / "candidate_A" / "code.py"
            iters.append({"iter": d.name, "passes": _passes(c), "trials": len(c["trial_results"]),
                          "errors": c["errors"], "is_fix_code":
                          code.exists() and hashlib.sha256(code.read_bytes()).hexdigest() == fix_sha})
    final = next((i for i in iters if i["is_fix_code"]), None)
    if final is None:
        print("WARNING: fix_code.py matches no evaluated iteration; final dev rate unknown")

    for d in FIX_DIRS:
        if (out / d).exists():
            (out / d).rename(fdir / d)
    if fx["parked"]:
        p = SIM / fx["parked"]
        for d in p.iterdir():
            d.rename(out / d.name)
        p.rmdir()
    fx.update({"iterations": iters, "final": final, "ended": time.strftime("%Y-%m-%d %H:%M:%S")})
    _write(fdir / "fix.json", fx)
    for i in iters:
        print(f"  {i['iter']}: {i['passes']}/{i['trials']}{'  <- fix_code.py' if i['is_fix_code'] else ''}")
    print(f"fix_{n} ({arm}) ended; outputs in {_rel(fdir)}; library {fx['to_snapshot']}")


# ── report ──────────────────────────────────────────────────────────────────

def _report(root: Path, arm: str) -> dict:
    tasks = libgen._manifest(root)["tasks"]
    rounds, fixes = [], []
    for n in range(ROUNDS + 1):
        p = root / _phase(arm, n) / "summary.json"
        if not p.exists():
            break
        rounds.append({t: v["mean_rate"] for t, v in _load(p)["tasks"].items()})
        if n < ROUNDS and (_fdir(root, arm, n + 1) / "fix.json").exists():
            fx = _load(_fdir(root, arm, n + 1) / "fix.json")
            if "ended" in fx:
                fin = fx["final"]
                fixes.append({"round": n + 1, "task": f"{fx['suite']}/{fx['task']}",
                              "start_rate": round(fx["start_passes"] / fx["trials"], 4),
                              "fix_rate": round(fin["passes"] / fin["trials"], 4) if fin else None})
    steps = []
    for n in range(1, len(rounds)):
        common = [t for t in rounds[n] if t in rounds[n - 1]]
        d = [rounds[n][t] - rounds[n - 1][t] for t in common]
        fixed_rates = {f["task"]: f["fix_rate"] for f in fixes[:n]}
        allt = [fixed_rates.get(t) if t in fixed_rates else rounds[n].get(t) for t in tasks]
        steps.append({
            "round": n, "library": _snap(arm, n), "fixed_task": fixes[n - 1]["task"],
            "mean_rate_unfixed": round(sum(rounds[n].values()) / len(rounds[n]), 4),
            "paired_delta": round(sum(d) / len(d), 4), "paired_tasks": len(common),
            "improved": sum(x > 0 for x in d), "worse": sum(x < 0 for x in d),
            # fixed tasks at their fix loop's dev rate (51-65, the seeds it was debugged on)
            "mean_rate_all_with_fixed": (round(sum(allt) / len(allt), 4)
                                         if None not in allt else None)})
    return {"arm": arm, "round_0_mean": round(sum(rounds[0].values()) / len(rounds[0]), 4) if rounds else None,
            "fixes": fixes, "steps": steps,
            "per_task": {t: [r.get(t) for r in rounds] for t in tasks}}


def cmd_report(a) -> None:
    for arm in a.arm or ARMS:
        if not (a.root / "round_0" / "summary.json").exists():
            sys.exit("round_0 not summarized yet")
        rep = _report(a.root, arm)
        (a.root / arm).mkdir(exist_ok=True)
        _write(a.root / arm / "report.json", rep)
        w = max(map(len, rep["per_task"]))
        nr = len(next(iter(rep["per_task"].values())))
        fixed_at = {f["task"]: f["round"] for f in rep["fixes"]}
        print(f"\n== {arm} ==  (mean success of one fresh program, seeds 51-65)")
        print(f"  {'task':<{w}} " + " ".join(f"{'r' + str(n):>6}" for n in range(nr)) + "  fixed")
        for t, rs in rep["per_task"].items():
            cells = " ".join(f"{x:>6.0%}" if x is not None else f"{'-':>6}" for x in rs)
            print(f"  {t:<{w}} {cells}  {('@' + str(fixed_at[t])) if t in fixed_at else ''}")
        for f in rep["fixes"]:
            fr = f"{f['fix_rate']:.0%}" if f["fix_rate"] is not None else "?"
            print(f"  fix {f['round']}: {f['task']}  start {f['start_rate']:.0%} -> fix_code {fr}")
        for s in rep["steps"]:
            print(f"  round {s['round']} ({s['library']}): paired delta {s['paired_delta']:+.1%} over "
                  f"{s['paired_tasks']} tasks (improved {s['improved']}, worse {s['worse']}); "
                  f"mean unfixed {s['mean_rate_unfixed']:.0%}")
        print(f"  -> {_rel(a.root / arm / 'report.json')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=SIM / "outputs/task_selection")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("init").set_defaults(fn=cmd_init)
    p = sp.add_parser("next")
    p.add_argument("--arm", choices=ARMS, required=True)
    p.set_defaults(fn=cmd_next)
    for name, fn in [("select", cmd_select), ("fix-begin", cmd_fix_begin), ("fix-end", cmd_fix_end)]:
        p = sp.add_parser(name)
        p.add_argument("--arm", choices=ARMS, required=True)
        p.add_argument("--n", type=int, choices=range(1, ROUNDS + 1), required=True)
        p.set_defaults(fn=fn)
    p = sp.add_parser("report")
    p.add_argument("--arm", choices=ARMS, nargs="*")
    p.set_defaults(fn=cmd_report)
    a = ap.parse_args()
    a.root = a.root if a.root.is_absolute() else (Path.cwd() / a.root)
    a.fn(a)


if __name__ == "__main__":
    main()
