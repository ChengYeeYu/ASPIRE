#!/usr/bin/env python3
"""Deterministic parent selection for the evosearch vs disagreement comparison.

In ASPIRE's evosearch runbook the coding agent picks the next round's parents itself
("seeded from top-3 survivors"). For a controlled comparison both arms call this script
instead, so the selection rule is code and the agent only writes the new candidates.

  select  --rule top3|disagreement --iter-dir RUN_DIR/iter_NN
          reads iter_NN/iter_summary.json, writes iter_NN/selection.json (parents for iter_NN+1)
  verify  --iter-dir RUN_DIR/iter_NN          (NN >= 1)
          checks iter_NN/parents.json only uses parents from iter_{NN-1}/selection.json

Standard library only. Run with .venv/bin/python3 from aspire/sim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

N_PARENTS = 3


def load_round(iter_dir: Path) -> tuple[list[dict], list[int]]:
    """Candidates with per-seed pass/fail vectors, sorted by name, and the round's seeds."""
    summary = json.loads((iter_dir / "iter_summary.json").read_text())
    seeds = sorted(summary["trial_seeds"])
    candidates = []
    for c in summary["candidates"]:
        by_seed = {int(t["trial"]): int(t["task_completed"]) for t in c["trial_results"]}
        missing = [s for s in seeds if s not in by_seed]
        if missing:
            raise SystemExit(f"{c['candidate']}: no result for seeds {missing} in {iter_dir}")
        candidates.append({
            "candidate": c["candidate"],
            "pass_count": sum(by_seed[s] for s in seeds),
            "pass_rate": round(sum(by_seed[s] for s in seeds) / len(seeds), 4),
            "errors": int(c.get("errors", 0)),
            "passed": [by_seed[s] for s in seeds],   # aligned with `seeds`
        })
    candidates.sort(key=lambda c: c["candidate"])
    return candidates, seeds


def select_top3(candidates: list[dict], seeds: list[int]) -> tuple[list[str], str]:
    """Highest pass_count first; ties broken by candidate name (A before B)."""
    ranked = sorted(candidates, key=lambda c: (-c["pass_count"], c["candidate"]))
    return [c["candidate"] for c in ranked[:N_PARENTS]], "pass_count desc, then candidate name asc"


def select_disagreement(candidates: list[dict], seeds: list[int]) -> tuple[list[str], str]:
    """TODO: the disagreement-selection rule.

    Input: `candidates` (sorted by name), each with `candidate`, `pass_count`, `pass_rate`,
    `errors`, and `passed` = 0/1 per seed aligned with `seeds`.
    Return: (exactly N_PARENTS candidate names, one-line description of the rule/tie-break).
    Must be deterministic: same input -> same output.
    """
    raise NotImplementedError("disagreement rule not implemented yet (scripts/tc1/select_parents.py)")


RULES = {"top3": select_top3, "disagreement": select_disagreement}


def cmd_select(args: argparse.Namespace) -> int:
    iter_dir = args.iter_dir.resolve()
    out = iter_dir / "selection.json"
    candidates, seeds = load_round(iter_dir)
    parents, tie_break = RULES[args.rule](candidates, seeds)
    names = {c["candidate"] for c in candidates}
    if len(parents) != N_PARENTS or len(set(parents)) != N_PARENTS or not set(parents) <= names:
        raise SystemExit(f"rule {args.rule!r} returned invalid parents: {parents}")
    by_name = {c["candidate"]: c for c in candidates}
    result = {
        "rule": args.rule,
        "tie_break": tie_break,
        "source_iter": iter_dir.name,
        "seeds": seeds,
        "parents": [f"{iter_dir.name}/{p}" for p in parents],
        "parent_pass_rates": [by_name[p]["pass_rate"] for p in parents],
        "candidates": candidates,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if out.exists():
        previous = json.loads(out.read_text())
        if previous.get("rule") != args.rule or previous.get("parents") != result["parents"]:
            raise SystemExit(f"{out} exists with different parents {previous.get('parents')}; refusing to overwrite")
        print(f"unchanged: {out}")
    else:
        out.write_text(json.dumps(result, indent=2) + "\n")
        print(f"wrote {out}")
    for p in parents:
        c = by_name[p]
        row = "".join("#" if x else "." for x in c["passed"])
        print(f"  parent {iter_dir.name}/{p}  {c['pass_count']}/{len(seeds)}  {row}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    iter_dir = args.iter_dir.resolve()
    number = int(iter_dir.name.split("_")[1])
    if number < 1:
        raise SystemExit("iter_00 has no parents to verify")
    prev = iter_dir.parent / f"iter_{number - 1:02d}"
    selection = json.loads((prev / "selection.json").read_text())
    parents_doc = json.loads((iter_dir / "parents.json").read_text())
    allowed = set(selection["parents"])
    problems, used = [], set()
    if parents_doc.get("selection") != selection["rule"]:
        problems.append(f"parents.json selection={parents_doc.get('selection')!r}, expected {selection['rule']!r}")
    for name, info in sorted(parents_doc.get("candidates", {}).items()):
        ps = info.get("parents", [])
        if not ps:
            problems.append(f"{name}: no parents listed")
        for p in ps:
            used.add(p)
            if p not in allowed:
                problems.append(f"{name}: parent {p} not in {prev.name}/selection.json {sorted(allowed)}")
    for p in sorted(allowed - used):
        print(f"note: selected parent {p} not used by any {iter_dir.name} candidate")
    if problems:
        print("FAIL"); [print("  " + p) for p in problems]
        return 1
    print(f"OK: {iter_dir.name}/parents.json uses only {prev.name}/selection.json parents ({selection['rule']})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("select")
    s.add_argument("--rule", choices=sorted(RULES), required=True)
    s.add_argument("--iter-dir", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("--iter-dir", type=Path, required=True)
    args = parser.parse_args()
    return cmd_select(args) if args.command == "select" else cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
