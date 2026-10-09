#!/bin/bash
# Re-evaluate one finished round's 8 candidates with a different --parallel-per-gpu and compare
# against the original eval: wall time, per-trial time, timeouts, and per-(candidate, seed) pass/fail.
# Results go to outputs/inspect/ only; the round itself is not touched.
#
#   bash scripts/tc1/bench_parallel.sh <ROUND_DIR> <PARALLEL> [candidate_X ...]   (default: all 8)
#   e.g. bash scripts/tc1/bench_parallel.sh outputs/claude_evosearch_r2/libero_goal_swap/put_the_bowl_on_the_stove/20260929_105729/iter_04 4
#
# Jupyter terminal (GPU node), Phase 1 env block, servers up, NO comparison run in progress.
# Takes ~30-70 min. Watch GPU memory in a second terminal: nvidia-smi -l 30
set -euo pipefail
SRC=${1:?round dir}; P=${2:?parallel per gpu}; shift 2; ONLY=("$@")
[ -f "$SRC/iter_summary.json" ] || { echo "no iter_summary.json in $SRC"; exit 1; }
B=outputs/inspect/bench_parallel_p${P}_$(date +%Y%m%d_%H%M)/$(basename "$SRC")
mkdir -p "$B"
for c in "$SRC"/candidate_*/; do
  n=$(basename "$c")
  [ ${#ONLY[@]} -gt 0 ] && [[ ! " ${ONLY[*]} " =~ " $n " ]] && continue
  mkdir -p "$B/$n"; cp "$c/code.py" "$B/$n/code.py"
done
SEEDS=$(.venv/bin/python3 -c "import json,sys; s=json.load(open(sys.argv[1])); print(*sorted({t['trial'] for c in s['candidates'] for t in c['trial_results']}))" "$SRC/iter_summary.json")
echo "bench dir: $B   parallel/GPU: $P   seeds: $SEEDS"
T0=$(date +%s)
.venv-libero/bin/python3 scripts/libero/evosearch_eval.py --iter-dir "$B" \
  --suite libero_goal_swap --task put_the_bowl_on_the_stove \
  --sim-gpus 0 --parallel-per-gpu "$P" --no-highlights --trial-seeds $SEEDS > "$B/eval.log" 2>&1
echo "wall time: $(( ($(date +%s) - T0) / 60 )) min" | tee "$B/wall_time.txt"
.venv/bin/python3 - "$SRC/iter_summary.json" "$B/iter_summary.json" <<'EOF'
import json, sys
def load(p):
    return {(c["candidate"], t["trial"]): t for c in json.load(open(p))["candidates"] for t in c["trial_results"]}
old, new = load(sys.argv[1]), load(sys.argv[2])
old = {k: v for k, v in old.items() if k in new}   # same candidates only
def stats(d):
    e = sorted(t["elapsed_s"] for t in d.values())
    return f"n={len(e)} p50={e[len(e)//2]:.0f}s p95={e[int(len(e)*.95)]:.0f}s max={e[-1]:.0f}s  >=170s: {sum(x >= 170 for x in e)}"
print("original:", stats(old)); print("bench   :", stats(new))
diff = [k for k in old if k in new and old[k]["task_completed"] != new[k]["task_completed"]]
print(f"passes: original {sum(t['task_completed'] for t in old.values())}, bench {sum(t['task_completed'] for t in new.values())}")
print(f"pass/fail differs on {len(diff)}/{len(old)} trials" + (": " + ", ".join(f"{c[-1]}{s}" for c, s in diff) if diff else ""))
for k in diff:
    print(f"  {k}: original {old[k]['elapsed_s']}s rc={old[k]['sandbox_rc']}  bench {new[k]['elapsed_s']}s rc={new[k]['sandbox_rc']}")
EOF
