#!/usr/bin/env python3
"""Time and token cost per run (fix loop, evosearch rN, disagreement rN).

Tokens come from Claude Code transcripts (<session>.jsonl + <session>/subagents/*.jsonl), each
API call counted once (dedup by requestId, per .claude/libero/analysis/token-calculate.md).
A session belongs to the run named in its first user message (the prompt files' opening lines).
Times come from the run's outputs: RUN_DIR stamp, each round's iter_summary.json mtime, and the
Stage 2 manifest.

  # TC1, from aspire/sim
  .venv/bin/python3 scripts/tc1/run_cost.py
  # laptop, on unpacked archives
  python3 run_cost.py --claude-dir <dir with the *.jsonl sessions> --outputs <unpacked outputs/>

Standard library only.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SUITE_TASK = "libero_goal_swap/put_the_bowl_on_the_stove"
FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def run_of(first_message: str) -> str | None:
    text = " ".join(first_message.split())
    m = re.search(r"as the EVOSEARCH arm, repetition (\d+)", text)
    if m:
        return f"evosearch_r{m.group(1)}"
    m = re.search(r"DISAGREEMENT-SELECTION arm, repetition (\d+)", text)
    if m:
        return f"disagreement_r{m.group(1)}"
    if "Run the LIBERO fix loop" in text:
        return "fixloop"
    return None


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read_jsonl(path: Path):
    for line in path.read_text(errors="replace").splitlines():
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def first_user_message(path: Path) -> str:
    for d in read_jsonl(path):
        if d.get("type") == "user" and not d.get("isSidechain"):
            content = d.get("message", {}).get("content", "")
            return content if isinstance(content, str) else json.dumps(content)
    return ""


def collect_calls(claude_dir: Path) -> dict[str, dict]:
    """run -> {"sessions": [...], "calls": {requestId: (timestamp, model, usage)}}."""
    runs: dict[str, dict] = defaultdict(lambda: {"sessions": [], "calls": {}})
    for main in sorted(claude_dir.glob("*.jsonl")):
        run = run_of(first_user_message(main))
        if run is None:
            continue
        runs[run]["sessions"].append(main.stem[:8])
        files = [main] + sorted((claude_dir / main.stem / "subagents").glob("*.jsonl"))
        for f in files:
            for d in read_jsonl(f):
                if d.get("type") != "assistant" or "usage" not in d.get("message", {}):
                    continue
                key = d.get("requestId") or d.get("uuid")
                if key in runs[run]["calls"]:
                    continue
                runs[run]["calls"][key] = (parse_ts(d["timestamp"]), d["message"].get("model", "?"),
                                           d["message"]["usage"])
    return runs


def run_times(outputs: Path, run: str) -> dict:
    """Round end times and Stage 2 span from the run's output folders (None if not found)."""
    if run == "fixloop":
        manifests = glob.glob(str(outputs / f"libero_fix_loop_eval/{SUITE_TASK}/runs/*/manifest.json"))
        rounds = []
    else:
        arm, rep = run.rsplit("_r", 1)
        run_dirs = sorted(glob.glob(str(outputs / f"claude_{arm}_r{rep}/{SUITE_TASK}/2*/")))
        rounds = []
        if run_dirs:
            for summary in sorted(Path(run_dirs[-1]).glob("iter_[0-9][0-9]/iter_summary.json")):
                rounds.append((summary.parent.name,
                               datetime.fromtimestamp(summary.stat().st_mtime, timezone.utc)))
        manifests = glob.glob(str(outputs / f"aspire_{arm}_eval_r{rep}/{SUITE_TASK}/runs/*/manifest.json"))
    stage2 = None
    if manifests:
        m = json.loads(Path(sorted(manifests)[-1]).read_text())
        stage2 = {"start": parse_ts(m["created_at"]), "end": parse_ts(m["updated_at"]),
                  "passes": m["passes"], "trials": m["trials"], "status": m["status"]}
    return {"rounds": rounds, "stage2": stage2}


def fmt_dur(td: timedelta | None) -> str:
    if td is None:
        return "-"
    minutes = int(td.total_seconds() // 60)
    return f"{minutes // 60}h{minutes % 60:02d}m"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default_claude = next(iter(sorted(Path.home().glob(".claude/projects/*ASPIRE-aspire-sim"))), None)
    parser.add_argument("--claude-dir", type=Path, default=default_claude)
    parser.add_argument("--outputs", type=Path, default=Path("outputs"))
    parser.add_argument("--tz-offset", type=float, default=8.0, help="hours added for local time (SGT = 8)")
    parser.add_argument("--json", type=Path, help="also write the numbers to this file")
    args = parser.parse_args()
    if args.claude_dir is None or not args.claude_dir.is_dir():
        raise SystemExit("no Claude project dir found; pass --claude-dir")
    local = timezone(timedelta(hours=args.tz_offset))

    report = {}
    for run, data in sorted(collect_calls(args.claude_dir).items()):
        calls = sorted(data["calls"].values(), key=lambda c: c[0])
        totals = defaultdict(int)
        by_model = defaultdict(lambda: defaultdict(int))
        for _, model, usage in calls:
            for f in FIELDS:
                totals[f] += usage.get(f, 0) or 0
                by_model[model][f] += usage.get(f, 0) or 0
            by_model[model]["calls"] += 1
        times = run_times(args.outputs, run)
        start = calls[0][0] if calls else None
        ends = [calls[-1][0]] if calls else []
        if times["stage2"]:
            ends.append(times["stage2"]["end"])
        end = max(ends) if ends else None

        # tokens per round: calls up to each round's iter_summary time; the rest = stage 2 / wrap-up
        buckets, bounds = [], [(name, t) for name, t in times["rounds"]]
        remaining = list(calls)
        for name, t in bounds:
            inside = [c for c in remaining if c[0] <= t]
            remaining = [c for c in remaining if c[0] > t]
            buckets.append((name, t, inside))
        buckets.append(("after last round" if bounds else "all", None, remaining))

        print(f"\n=== {run}   sessions: {', '.join(data['sessions'])}")
        if start and end:
            print(f"  wall clock : {start.astimezone(local):%d %b %H:%M} -> {end.astimezone(local):%d %b %H:%M}"
                  f"  ({fmt_dur(end - start)}, includes idle time between jobs)")
        agent_span = (calls[-1][0] - calls[0][0]) if calls else None
        print(f"  agent span : {fmt_dur(agent_span)} (first to last model call)")
        prev = start
        for name, t, inside in buckets:
            out = sum(c[2].get("output_tokens", 0) for c in inside)
            total_in = sum(sum(c[2].get(f, 0) or 0 for f in FIELDS[:3]) for c in inside)
            when = f"done {t.astimezone(local):%H:%M} ({fmt_dur(t - prev) if prev else '-'})" if t else ""
            print(f"  {name:<16} {when:<24} calls={len(inside):>4}  input={total_in:>12,}  output={out:>9,}")
            prev = t or prev
        if times["stage2"]:
            s = times["stage2"]
            print(f"  stage 2    : {s['start'].astimezone(local):%d %b %H:%M} -> {s['end'].astimezone(local):%H:%M}"
                  f" ({fmt_dur(s['end'] - s['start'])})  {s['passes']}/{s['trials']} {s['status']}")
        print(f"  tokens     : calls={len(calls):,}  " + "  ".join(f"{f.replace('_input_tokens', '').replace('_tokens', '')}={totals[f]:,}" for f in FIELDS))
        for model, v in sorted(by_model.items()):
            print(f"    {model:<22} calls={v['calls']:>4}  " + "  ".join(f"{f.replace('_input_tokens', '').replace('_tokens', '')}={v[f]:,}" for f in FIELDS))
        report[run] = {
            "sessions": data["sessions"], "calls": len(calls), "tokens": dict(totals),
            "by_model": {m: dict(v) for m, v in by_model.items()},
            "start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
            "rounds": [{"round": n, "end": t.isoformat(), "calls": len(i),
                        "output_tokens": sum(c[2].get("output_tokens", 0) for c in i)} for n, t, i in buckets if t],
            "stage2": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in times["stage2"].items()}
                      if times["stage2"] else None,
        }
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
