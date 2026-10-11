# Library gain: does a skill-library update help the OTHER tasks?

Measure the library alone, without debugging the tasks it is applied to:
- **before**: K fresh programs per task, written zero-shot from library L0, run on fixed seeds.
- **fix**: a fix loop on ONE chosen task promotes skills, giving library L1 (separate step, not here).
- **after**: K fresh programs for the other tasks from L1, same K, seeds, probe and codegen prompt.
- **gain** = after minus before (mean success of one fresh program), on the other tasks only.
- **noise**: a second "before" (`before_b`, same L0) shows how much the numbers move with no library change.

Files: `libgen.py` (bookkeeping + eval), `libgen_codegen_prompt.md` (Claude session that writes the
programs, one subagent per program), `skills_snapshot.sh save-git` (L0 = library as committed).
Defaults: `libero_goal_swap`, 10 tasks, K=4, seeds 1-10, probe seed 100, 4 workers on GPU 0.

Same session conventions as EXPERIMENT.md (Phase 0/1: push, `git pull`, Jupyter terminal + env block).
`ROOT=outputs/libgen_goal_swap`.

## Once: L0, manifest, probes
```bash
# Jupyter terminal, ~/ASPIRE/aspire/sim
bash scripts/tc1/skills_snapshot.sh save-git L0_clean           # library as committed (pre-fix-loop)
bash scripts/tc1/skills_snapshot.sh restore L0_clean            # working tree had after_fixloop (saved, recoverable)
ROOT=outputs/libgen_goal_swap
.venv-libero/bin/python3 scripts/tc1/libgen.py init  --root $ROOT --suite libero_goal_swap
.venv-libero/bin/python3 scripts/tc1/libgen.py probe --root $ROOT   # ~1-2 min/task, resumable
head -3 $ROOT/probe/*.txt                                         # every file has TASK_LANGUAGE; failures -> probe/<task>.err.log
```

## One phase (before, before_b, after_<arm>)
```bash
PHASE=before   SNAP=L0_clean   EXCL=""                          # after: PHASE=after_<arm> SNAP=<L1 snapshot> EXCL="--exclude <task>"
bash scripts/tc1/skills_snapshot.sh restore $SNAP
.venv/bin/python3 scripts/tc1/libgen.py phase-start --root $ROOT --phase $PHASE --snapshot $SNAP $EXCL

# codegen (resume = same command)
claude "$(sed -e "s|{{ROOT}}|$ROOT|g" -e "s|{{PHASE}}|$PHASE|g" scripts/tc1/libgen_codegen_prompt.md)"
.venv/bin/python3 scripts/tc1/libgen.py status --root $ROOT --phase $PHASE   # all slots filled, library OK

# eval: detached, resumable (finished tasks skipped; a crashed task is re-run whole, partial eval kept as eval_partial_*)
setsid nohup .venv-libero/bin/python3 scripts/tc1/libgen.py eval --root $ROOT --phase $PHASE \
  > $ROOT/$PHASE/eval_driver.log 2>&1 &
tail -f $ROOT/$PHASE/eval_driver.log                             # per-task log: $ROOT/$PHASE/<task>/eval.log

.venv/bin/python3 scripts/tc1/libgen.py summarize --root $ROOT --phase $PHASE
bash scripts/tc1/skills_snapshot.sh check $SNAP                  # nothing touched the library
```
Cost per phase (10 tasks): 40 codegen subagents; eval 400 trials, about 2 h at 4 workers
(bench: 120 trials in 34 min) plus ~1 min warm-up per task.

## Gain
```bash
.venv/bin/python3 scripts/tc1/libgen.py gain --root $ROOT --before before --after after_<arm> --noise before_b
```
Writes `$ROOT/gain_after_<arm>.json`: per-task before/after/delta, mean delta over the non-excluded
tasks, and the noise row (before_b minus before). A gain smaller than the noise is not a result.

## Rules
- Nothing may edit `.claude/libero/skills/` while a phase is in codegen or eval (`eval` refuses if
  the library sha changed since `phase-start`; `status` shows it).
- Don't edit `libgen_codegen_prompt.md` between phases; `gain` warns if phases used different prompts.
- Seeds 1-10 measure; seed 100 is only the probe. Fix loops debug on 51-65, held-out 1-50.
- `summary.json` per task also has `best_rate`, `any_pass_rate`, `seed_disagreement` (seeds where
  some but not all K programs pass) -- inputs for choosing which task to fix.
