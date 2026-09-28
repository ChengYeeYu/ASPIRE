Run LIBERO Evolutionary Search per .claude/libero/evosearch/INSTRUCTIONS.md for ONE task, as the
EVOSEARCH arm, repetition {{REP}}, of a controlled comparison. Approved deviations below; do not
stop on them in preflight.

Fixed inputs
- SUITE=libero_goal_swap  TASK=put_the_bowl_on_the_stove
- START_CODE = outputs/libero_fix_loop/libero_goal_swap/put_the_bowl_on_the_stove/fix_code.py
- BASELINE_RATE = pass_rate in outputs/libero_fix_loop/libero_goal_swap/put_the_bowl_on_the_stove/validation_result.json
  (report it; if >= 80%, report and stop).
- Everywhere the runbook says outputs/libero_baseline_image_diff_gemini/$SUITE/$TASK/fix_code.py,
  use START_CODE (candidate_A seeding AND the Step 7 fallback).

Output roots (this arm + repetition only)
- EVOSEARCH_DIR = outputs/claude_evosearch_r{{REP}}
- EVALDIR       = outputs/aspire_evosearch_eval_r{{REP}}
- Do not write outputs/working_codes/*_evosearch.py (it would collide across arms/repetitions).

Frozen settings (must stay identical to the disagreement arm)
- K = 8 candidates per round; candidate_A in iter_00 = START_CODE verbatim.
- Dev seeds 51-65 only during rounds: --trial-seeds 51 52 53 54 55 56 57 58 59 60 61 62 63 64 65.
- Stop when best candidate >= 80% on seeds 51-65, or after 5 rounds (iter_00..iter_04).
  No plateau stop, no early stop.
- Parent selection: next round's 8 candidates are seeded from the top-3 candidates of the current
  round by pass_rate (runbook default).
- evosearch_eval.py: --sim-gpus 0 --parallel-per-gpu 2 --no-highlights (use 1 for BOTH arms
  if CUDA OOM, and tell me).
- Subagent model: dispatch with NO model override, so it inherits this session's /model.
- Record parents: for every round N >= 1 write $RUN_DIR/iter_NN/parents.json:
  {"selection": "top3_pass_rate", "candidates": {"candidate_A": {"parents": ["iter_MM/candidate_X", ...],
   "parent_pass_rates": [..]}, ...}}

Hardware (NTU TC1, 1 V100, 6 h SLURM job)
- GPU 0 only; SAM3/GraspNet/PyRoKi already run on it (8114-8116). Never start/stop them.
- /tmp is wiped per job: every script, pid file, snapshot and log goes under outputs/.

Skill library is FROZEN
- Nobody (you or the subagent) edits .claude/libero/skills/. Patterns go into findings.md only.
- Run `bash scripts/tc1/skills_snapshot.sh check after_fixloop` in preflight and in the final report.

Agents
- Exactly ONE evosearch subagent (GPU: 0). No other agents (no Explore/Plan helpers).
- The subagent does Stage 1 (Steps 0-7a) + findings.md and returns. It does NOT run Stage 2
  (skip Step 7b); you run Stage 2 as below.

Stage 2 (you, in the background, after the subagent returns)
- If evosearch_best_code.py is a new candidate:
    .venv-libero/bin/python3 scripts/libero/run_fix_loop_validation.py \
      --suite libero_goal_swap --task put_the_bowl_on_the_stove --gpu 0 \
      --fix-code outputs/claude_evosearch_r{{REP}}/libero_goal_swap/put_the_bowl_on_the_stove/evosearch_best_code.py \
      --output-dir outputs/aspire_evosearch_eval_r{{REP}} --seeds $(seq 1 50) --resume
- If it fell back to START_CODE: do not re-run; record "fallback, held-out = BASELINE_RATE".

Resuming (an earlier 6 h job may have ended mid-run)
- evosearch_best_code.py exists -> skip Stage 1; run/resume Stage 2 only.
- A RUN_DIR exists without it -> ONE new subagent that continues that RUN_DIR: keep finished rounds
  (those with iter_summary.json), re-evaluate an unfinished round, never start a new RUN_DIR.

Final report
- BASELINE_RATE; candidate_A's iter_00 dev rate; per round: best / mean / parents' pass rates;
  first round with a candidate beating candidate_A's dev rate, and first round >= 80%;
  final code path; Stage 2 passes/50 and manifest path; skills check result.

Never push to any remote. Start with the preflight report and wait for my go.
