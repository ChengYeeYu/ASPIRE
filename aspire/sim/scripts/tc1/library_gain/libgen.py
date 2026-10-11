#!/usr/bin/env python3
"""Library-gain measurement: how much does a skill-library update help the OTHER tasks?

One ROOT holds one experiment over a task list (default: 10 tasks of one suite). A task id is
"<suite>/<task>", so one ROOT may mix suites:
  ROOT/manifest.json                        tasks, K, seeds, probe seed  (init)
  ROOT/probe/<id>.txt                       scripted scene probe, shared by all phases (probe)
  ROOT/<phase>/phase.json                   library snapshot + sha, excluded tasks (phase-start)
  ROOT/<phase>/<id>/candidate_X/code.py     written by codegen subagents (libgen_codegen_prompt.md)
  ROOT/<phase>/<id>/iter_summary.json       written by evosearch_eval.py (eval)
  ROOT/<phase>/summary.json                 per-task rates + disagreement (summarize)

Phases: "before" (library L0), optionally "before_b" (L0 again = noise baseline),
"after_<arm>" (library L1 from a fix loop on one task, that task excluded).

  .venv-libero/bin/python3 scripts/tc1/library_gain/libgen.py init  --root R --suite libero_goal_swap [--tasks <suite>/<task> ...]
  .venv-libero/bin/python3 scripts/tc1/library_gain/libgen.py probe --root R
  .venv/bin/python3        scripts/tc1/library_gain/libgen.py phase-start --root R --phase before --snapshot L0_clean
  (codegen: claude "$(sed ... scripts/tc1/library_gain/libgen_codegen_prompt.md)")
  .venv/bin/python3        scripts/tc1/library_gain/libgen.py status --root R --phase before
  .venv-libero/bin/python3 scripts/tc1/library_gain/libgen.py eval  --root R --phase before     # detached, resumable
  .venv/bin/python3        scripts/tc1/library_gain/libgen.py summarize --root R --phase before
  .venv/bin/python3        scripts/tc1/library_gain/libgen.py gain --root R --before before --after after_x [--noise before_b]
Run from aspire/sim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import string
import subprocess
import sys
import time
from pathlib import Path

SIM = Path(__file__).resolve().parents[3]
SKILLS = SIM / ".claude/libero/skills"
SNAPSHOTS = SIM / "outputs/skill_snapshots"
CODEGEN_PROMPT = SIM / "scripts/tc1/library_gain/libgen_codegen_prompt.md"
EVAL = SIM / "scripts/libero/evosearch_eval.py"
REPLAY = SIM / "scripts/libero/replay_trial.py"
CONFIG = SIM / "env_configs/libero/franka_libero_traced.yaml"
LIBERO_PY = SIM / ".venv-libero/bin/python3"

PROBE_PROMPTS = [
    "bowl", "black bowl", "plate", "stove", "cabinet", "drawer", "top drawer", "middle drawer",
    "wine bottle", "rack", "wine rack", "cream cheese", "mug", "basket", "box", "bottle",
    "ramekin", "cookie box", "alphabet soup", "salad dressing", "tomato sauce", "ketchup",
    "bbq sauce", "butter", "milk", "chocolate pudding", "orange juice",
]


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


def _write(p: Path, obj: dict) -> None:
    p.write_text(json.dumps(obj, indent=2) + "\n")


def _manifest(root: Path) -> dict:
    p = root / "manifest.json"
    if not p.exists():
        sys.exit(f"no {p} -- run init first")
    return _load(p)


def _split(tid: str) -> tuple[str, str]:
    """Task id "<suite>/<task>" -> (suite, task)."""
    suite, _, task = tid.partition("/")
    if not task:
        sys.exit(f"task id {tid!r} is not <suite>/<task>")
    return suite, task


def _candidates(k: int) -> list[str]:
    return [f"candidate_{c}" for c in string.ascii_uppercase[:k]]


def _parse_seeds(s: str) -> list[int]:
    if "-" in s and "," not in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in s.split(",")]


def _library_sha() -> str:
    """One sha over the current skill library (relative path + content of every file)."""
    h = hashlib.sha256()
    for f in sorted(p for p in SKILLS.rglob("*") if p.is_file()):
        h.update(str(f.relative_to(SKILLS)).encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def _file_sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ── init / probe ────────────────────────────────────────────────────────────

def cmd_init(a) -> None:
    root = a.root
    if (root / "manifest.json").exists():
        sys.exit(f"{root}/manifest.json exists, refusing to overwrite")
    from libero import benchmark as libero_benchmark  # needs .venv-libero
    bench = libero_benchmark.get_benchmark_dict()
    names: dict[str, list[str]] = {}

    def suite_tasks(suite: str) -> list[str]:
        if suite not in names:
            if suite not in bench:
                sys.exit(f"unknown suite {suite!r}")
            b = bench[suite]()
            names[suite] = [b.get_task(i).name for i in range(b.n_tasks)]
        return names[suite]

    tasks = [t if "/" in t else f"{a.suite}/{t}" for t in a.tasks or []]
    if not tasks:
        tasks = [f"{a.suite}/{t}" for t in suite_tasks(a.suite)]
    tasks = tasks[: a.max_tasks]
    for t in tasks:
        suite, task = _split(t)
        if task not in suite_tasks(suite):
            sys.exit(f"{task!r} is not a task of {suite}")
    seeds = _parse_seeds(a.seeds)
    if a.probe_seed in seeds:
        sys.exit("probe seed must not be one of the measurement seeds")
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "manifest.json", {
        "tasks": tasks, "k": a.k, "seeds": seeds,
        "probe_seed": a.probe_seed, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    print(f"{root}/manifest.json: {len(tasks)} tasks, K={a.k}, seeds {seeds[0]}..{seeds[-1]}")
    for t in tasks:
        print(f"  {t}")


PROBE_BODY = """
import numpy as np
# in the REPL `env` is the code env; programs see its low_level_env as `env`
print("TASK_LANGUAGE:", getattr(env, "low_level_env", env).handle.task_language, flush=True)
_o = get_observation()
_rgb = _o["agentview"]["images"]["rgb"]
_d = _o["agentview"]["images"]["depth"]
_d = _d[:, :, 0] if _d.ndim == 3 else _d
_K, _T = _o["agentview"]["intrinsics"], _o["agentview"]["pose_mat"]
print("EEF_POSE: (robot base frame: x y z, quat wxyz, gripper)", np.round(np.asarray(_o["robot_cartesian_pos"]), 3).tolist(), flush=True)
for _p in PROMPTS:
    try:
        _ms = segment_sam3_text_prompt(_rgb, _p)
    except Exception as _e:
        print(f"{_p}: ERROR {_e}", flush=True); continue
    if not _ms:
        print(f"{_p}: no masks", flush=True); continue
    _ms = sorted(_ms, key=lambda m: -m["score"])
    _line = f"{_p}: {len(_ms)} masks"
    for _m in _ms[:3]:
        _pts = mask_to_world_points(_m["mask"].astype(np.uint8), _d, _K, _T)
        if _pts is None or len(_pts) < 10:
            _line += f" | score={_m['score']:.2f} (no 3D points)"; continue
        _bb = get_oriented_bounding_box_from_3d_points(_pts)
        _line += (f" | score={_m['score']:.2f} center={np.round(_bb['center'], 3).tolist()}"
                  f" extent={np.round(_bb['extent'], 3).tolist()} z_max={np.max(_pts[:, 2]):.3f}")
    print(_line, flush=True)
print("PROBE_DONE", flush=True)
"""


def cmd_probe(a) -> None:
    m = _manifest(a.root)
    out = a.root / "probe"
    out.mkdir(exist_ok=True)
    body = out / "_probe_body.py"
    body.write_text(f"PROMPTS = {PROBE_PROMPTS!r}\n" + PROBE_BODY)
    for tid in m["tasks"]:
        suite, task = _split(tid)
        dst = out / f"{tid}.txt"
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and "PROBE_DONE" in dst.read_text():
            print(f"skip (done): {tid}")
            continue
        print(f"probing {tid} on seed {m['probe_seed']} ...", flush=True)
        cmd = [str(LIBERO_PY), str(REPLAY), "--args.suite", suite, "--args.task", task,
               "--args.trial", str(m["probe_seed"]), "--args.interactive",
               "--args.config", str(CONFIG), "--args.output-dir", str(out / "_replay" / tid)]
        r = subprocess.run(cmd, input=f"exec(open({str(body)!r}).read())\n", text=True,
                           capture_output=True, cwd=SIM, timeout=900)
        lines = [re.sub(r"^(?:(?:>>>|\.\.\.) )+", "", ln) for ln in r.stdout.splitlines()]  # strip REPL prompts
        keep = [ln for ln in lines
                if ln.startswith(("TASK_LANGUAGE:", "EEF_POSE:", "PROBE_DONE"))
                or any(ln.startswith(p + ":") for p in PROBE_PROMPTS)]
        header = (f"# Scene probe: {suite} / {task}, seed {m['probe_seed']} (not a measurement seed)\n"
                  f"# SAM3 text prompts on the agentview image at reset; top 3 masks each; world frame, metres.\n"
                  f"# Positions differ per seed -- localise at run time, never hard-code these numbers.\n")
        dst.write_text(header + "\n".join(keep) + "\n")
        if "PROBE_DONE" not in keep:
            (out / f"{tid}.err.log").write_text(r.stdout[-20000:] + "\n--- stderr ---\n" + r.stderr[-20000:])
            print(f"  FAILED (see probe/{tid}.err.log)")
        else:
            print(f"  ok: {keep[0]}")


# ── phases ──────────────────────────────────────────────────────────────────

def cmd_phase_start(a) -> None:
    m = _manifest(a.root)
    pdir = a.root / a.phase
    if (pdir / "phase.json").exists():
        sys.exit(f"{pdir}/phase.json exists -- phase already started")
    snap = SNAPSHOTS / a.snapshot
    if not (snap / "SHA256SUMS").exists():
        sys.exit(f"no snapshot {snap}")
    r = subprocess.run(["bash", "scripts/tc1/common/skills_snapshot.sh", "check", a.snapshot], cwd=SIM)
    if r.returncode != 0:
        sys.exit(f"skill library != snapshot {a.snapshot}: run skills_snapshot.sh restore {a.snapshot} first")
    for t in a.exclude:
        if t not in m["tasks"]:
            sys.exit(f"--exclude {t}: not in manifest tasks")
    missing = [t for t in m["tasks"] if not (a.root / "probe" / f"{t}.txt").exists()]
    if missing:
        sys.exit(f"probe missing for {missing} -- run probe first")
    tasks = [t for t in m["tasks"] if t not in a.exclude]
    for t in tasks:
        for c in _candidates(m["k"]):
            (pdir / t / c).mkdir(parents=True, exist_ok=True)
    _write(pdir / "phase.json", {
        "phase": a.phase, "snapshot": a.snapshot, "library_sha": _library_sha(),
        "codegen_prompt_sha": _file_sha(CODEGEN_PROMPT), "excluded": a.exclude, "tasks": tasks,
        "note": a.note, "started": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    print(f"{pdir}: {len(tasks)} tasks x {m['k']} candidates; library {a.snapshot} "
          f"sha {_library_sha()[:12]}; excluded {a.exclude or 'none'}")


def _phase(root: Path, phase: str) -> dict:
    p = root / phase / "phase.json"
    if not p.exists():
        sys.exit(f"no {p} -- run phase-start first")
    return _load(p)


def cmd_status(a) -> None:
    m, ph = _manifest(a.root), _phase(a.root, a.phase)
    lib_ok = _library_sha() == ph["library_sha"]
    print(f"phase {a.phase}: library {ph['snapshot']} {'OK' if lib_ok else 'CHANGED (!)'}")
    n_code = n_eval = 0
    w = max(map(len, ph["tasks"]))
    for t in ph["tasks"]:
        have = [c[-1] for c in _candidates(m["k"]) if (a.root / a.phase / t / c / "code.py").exists()]
        done = (a.root / a.phase / t / "iter_summary.json").exists()
        n_code += len(have)
        n_eval += done
        print(f"  {t:<{w}} code {''.join(have) or '-':<{m['k']}}  {'evaluated' if done else ''}")
    print(f"code {n_code}/{len(ph['tasks']) * m['k']}, evaluated tasks {n_eval}/{len(ph['tasks'])}")
    if not lib_ok:
        sys.exit(1)


def cmd_eval(a) -> None:
    m, ph = _manifest(a.root), _phase(a.root, a.phase)
    if _library_sha() != ph["library_sha"]:
        sys.exit("skill library changed since phase-start -- refusing to evaluate")
    cands = _candidates(m["k"])
    missing = [f"{t}/{c}" for t in ph["tasks"] for c in cands
               if not (a.root / a.phase / t / c / "code.py").exists()]
    if missing:
        sys.exit(f"{len(missing)} code.py missing, e.g. {missing[:3]} -- finish codegen first")
    seeds = [str(s) for s in m["seeds"]]
    for t in ph["tasks"]:
        tdir = a.root / a.phase / t
        if (tdir / "iter_summary.json").exists():
            print(f"skip (done): {t}", flush=True)
            continue
        stamp = time.strftime("%Y%m%d_%H%M%S")
        for c in cands:  # partial outputs of a crashed eval: keep, but out of the way
            if (tdir / c / "eval").exists():
                (tdir / c / "eval").rename(tdir / c / f"eval_partial_{stamp}")
        print(f"[{time.strftime('%H:%M:%S')}] eval {t}", flush=True)
        suite, task = _split(t)
        cmd = [str(LIBERO_PY), str(EVAL), "--iter-dir", str(tdir), "--suite", suite, "--task", task,
               "--trials", str(len(seeds)), "--trial-seeds", *seeds, "--config", str(CONFIG),
               "--sim-gpus", *[str(g) for g in a.sim_gpus], "--parallel-per-gpu", str(a.parallel_per_gpu),
               "--no-highlights"]
        with open(tdir / "eval.log", "a") as log:
            r = subprocess.run(cmd, cwd=SIM, stdout=log, stderr=subprocess.STDOUT)
        if r.returncode != 0 or not (tdir / "iter_summary.json").exists():
            sys.exit(f"eval failed for {t} (rc={r.returncode}), see {tdir}/eval.log; re-run to resume")
    print("all tasks evaluated")


# ── summarize / gain ────────────────────────────────────────────────────────

def _task_stats(summary: dict, seeds: list[int]) -> dict:
    cands = summary["candidates"]
    if summary["trial_seeds"] != seeds:
        sys.exit(f"{summary['task']}: seeds {summary['trial_seeds']} != manifest {seeds}")
    passed = {c["candidate"]: {r["trial"] for r in c["trial_results"] if r["task_completed"]} for c in cands}
    rates = {c["candidate"]: c["pass_rate"] for c in cands}
    n_pass_per_seed = [sum(s in p for p in passed.values()) for s in seeds]
    k = len(cands)
    return {
        "mean_rate": round(sum(rates.values()) / k, 4),           # expected success of one fresh program
        "best_rate": max(rates.values()),
        "any_pass_rate": round(sum(n > 0 for n in n_pass_per_seed) / len(seeds), 4),
        "programs_with_any_pass": sum(bool(p) for p in passed.values()),
        # seeds where the K programs disagree (some pass, some fail)
        "seed_disagreement": round(sum(0 < n < k for n in n_pass_per_seed) / len(seeds), 4),
        "rates": dict(sorted(rates.items())),
        "errors": sum(c["errors"] for c in cands),
        # per program, one character per seed (in "seeds" order): 1 = pass, 0 = fail
        "pass_matrix": {c: "".join("1" if s in passed[c] else "0" for s in seeds) for c in sorted(passed)},
    }


def _summarize(root: Path, phase: str) -> dict:
    m, ph = _manifest(root), _phase(root, phase)
    tasks = {}
    for t in ph["tasks"]:
        p = root / phase / t / "iter_summary.json"
        if not p.exists():
            sys.exit(f"not evaluated: {phase}/{t}")
        tasks[t] = _task_stats(_load(p), m["seeds"])
    means = [s["mean_rate"] for s in tasks.values()]
    return {"phase": phase, "snapshot": ph["snapshot"], "k": m["k"], "seeds": m["seeds"],
            "mean_rate_over_tasks": round(sum(means) / len(means), 4), "tasks": tasks}


def cmd_summarize(a) -> None:
    s = _summarize(a.root, a.phase)
    _write(a.root / a.phase / "summary.json", s)
    print(f"phase {a.phase} (library {s['snapshot']}, K={s['k']}, {len(s['seeds'])} seeds)")
    w = max(map(len, s["tasks"]))
    print(f"  {'task':<{w}} {'mean':>5} {'best':>5} {'any':>5} {'disagr':>6}  per-candidate")
    for t, st in s["tasks"].items():
        per = " ".join(f"{r:.0%}" for r in st["rates"].values())
        print(f"  {t:<{w}} {st['mean_rate']:>5.0%} {st['best_rate']:>5.0%} {st['any_pass_rate']:>5.0%} "
              f"{st['seed_disagreement']:>6.0%}  {per}")
    print(f"  mean over tasks: {s['mean_rate_over_tasks']:.1%}   -> {a.root / a.phase / 'summary.json'}")


def cmd_gain(a) -> None:
    before, after = _summarize(a.root, a.before), _summarize(a.root, a.after)
    excluded = set(_phase(a.root, a.after)["excluded"])
    tasks = [t for t in after["tasks"] if t in before["tasks"] and t not in excluded]
    noise = _summarize(a.root, a.noise) if a.noise else None
    shas = {ph: _phase(a.root, ph)["codegen_prompt_sha"] for ph in filter(None, [a.before, a.after, a.noise])}
    if len(set(shas.values())) > 1:
        print(f"WARNING: phases used different codegen prompts: { {k: v[:12] for k, v in shas.items()} }")
    rows, deltas, nds = [], [], []
    print(f"gain: {a.after} ({after['snapshot']}) minus {a.before} ({before['snapshot']}); "
          f"excluded {sorted(excluded) or 'none'}")
    w = max(map(len, tasks))
    hdr = f"  {'task':<{w}} {'before':>6} {'after':>6} {'delta':>6}"
    print(hdr + (f" {'noise':>6}" if noise else ""))
    for t in tasks:
        b, f_ = before["tasks"][t]["mean_rate"], after["tasks"][t]["mean_rate"]
        d = f_ - b
        deltas.append(d)
        row = {"task": t, "before": b, "after": f_, "delta": round(d, 4)}
        line = f"  {t:<{w}} {b:>6.0%} {f_:>6.0%} {d:>+6.0%}"
        if noise and t in noise["tasks"]:
            nd = noise["tasks"][t]["mean_rate"] - b
            nds.append(nd)
            row["noise_delta"] = round(nd, 4)
            line += f" {nd:>+6.0%}"
        rows.append(row)
        print(line)
    mean_d = sum(deltas) / len(deltas)
    out = {"before": a.before, "after": a.after, "noise": a.noise, "excluded": sorted(excluded),
           "tasks": rows, "mean_delta": round(mean_d, 4),
           "improved": sum(d > 0 for d in deltas), "worse": sum(d < 0 for d in deltas)}
    print(f"  mean delta over {len(tasks)} tasks: {mean_d:+.1%}  "
          f"(improved {out['improved']}, worse {out['worse']})")
    if noise:
        out["noise_mean_abs_delta"] = round(sum(abs(x) for x in nds) / len(nds), 4)
        out["noise_mean_delta"] = round(sum(nds) / len(nds), 4)
        print(f"  noise ({a.noise} vs {a.before}, same library): mean {out['noise_mean_delta']:+.1%}, "
              f"mean |delta| per task {out['noise_mean_abs_delta']:.1%}")
    dst = a.root / f"gain_{a.after.replace('/', '__')}.json"
    _write(dst, out)
    print(f"  -> {dst}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("init")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--suite", default="libero_goal_swap", help="suite for --tasks given without a suite/ prefix")
    p.add_argument("--tasks", nargs="*", help="<suite>/<task> ids; default: all tasks of --suite. "
                   "Checked against the installed suites (needs .venv-libero)")
    p.add_argument("--max-tasks", type=int, default=10)
    p.add_argument("--k", type=int, default=4, help="programs per task")
    p.add_argument("--seeds", default="1-10", help="measurement seeds, '1-10' or '1,2,3'")
    p.add_argument("--probe-seed", type=int, default=100)
    p.set_defaults(fn=cmd_init)

    p = sp.add_parser("probe")
    p.add_argument("--root", type=Path, required=True)
    p.set_defaults(fn=cmd_probe)

    p = sp.add_parser("phase-start")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--phase", required=True)
    p.add_argument("--snapshot", required=True, help="outputs/skill_snapshots/<name> the library must match")
    p.add_argument("--exclude", nargs="*", default=[], help="task(s) the library update was made on")
    p.add_argument("--note", default="")
    p.set_defaults(fn=cmd_phase_start)

    for name, fn in [("status", cmd_status), ("summarize", cmd_summarize)]:
        p = sp.add_parser(name)
        p.add_argument("--root", type=Path, required=True)
        p.add_argument("--phase", required=True)
        p.set_defaults(fn=fn)

    p = sp.add_parser("eval")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--phase", required=True)
    p.add_argument("--sim-gpus", type=int, nargs="+", default=[0])
    p.add_argument("--parallel-per-gpu", type=int, default=4)
    p.set_defaults(fn=cmd_eval)

    p = sp.add_parser("gain")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--before", default="before")
    p.add_argument("--after", required=True)
    p.add_argument("--noise", help="second phase on the SAME library as --before")
    p.set_defaults(fn=cmd_gain)

    a = ap.parse_args()
    a.root = a.root if a.root.is_absolute() else (Path.cwd() / a.root)
    a.fn(a)


if __name__ == "__main__":
    main()
