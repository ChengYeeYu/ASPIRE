Run a LIBERO fix loop on ONE task to grow the shared skill library, for the task-selection
experiment (arm {{ARM}}, step {{N}}). It follows .claude/libero/fix-loop/ (main-agent-prompt.md
"6. Update skills" for promotion, subagent-prompt.md for tools and findings.md), with the approved
deviations below; do not stop on them in preflight.

Scope
- ONE task: SUITE={{SUITE}} TASK={{TASK}}. gen_progress.py may list other pending tasks -- ignore them.
- TASK_DIR=outputs/libero_fix_loop/{{SUITE}}/{{TASK}}
- Start library = snapshot {{FROM}} (it may be EMPTY: no skill files at all). The task does not
  start from scratch: $TASK_DIR/start_code.py is the best of 3 zero-shot programs for this task,
  and $TASK_DIR/iters/iter_0/ holds it (candidate_A/code.py) with its run on seeds 51-65
  (iter_summary.json, candidate_A/eval/trial_*/{trace.json,summary.txt}; no keyframes).
- Development seeds 51-65 only. No Stage 2, no seeds 1-50.
- Preflight must show
    bash scripts/tc1/common/skills_snapshot.sh check {{FROM}}   -> OK
  $TASK_DIR containing only start_code.py and iters/iter_0 (or later iterations when resuming),
  and outputs/libero_fix_loop_debug, outputs/working_codes absent (unless resuming).
  If not, report and stop.

Hardware (NTU TC1, SLURM job, 6 h wall limit)
- Single V100 = GPU 0. SAM3/GraspNet/PyRoKi already run on it (ports 8114-8116). Never start/stop them.
- /tmp is wiped when the job ends: all scratch code and replay outputs go under $TASK_DIR or
  outputs/libero_fix_loop_debug/, never /tmp.

Subagents
- Exactly ONE subagent in total, with NO model override, briefed with the template below
  (fill the placeholders; add nothing task-specific). Do not spawn any other agents.
- If it returns without fix_code.py or findings.md, do NOT re-dispatch; tell me and wait.

Isolation (the library update must come from this task's own evidence only)
- Never open, list or search outputs/task_selection/, outputs/libgen*, outputs/skill_snapshots/
  (only via skills_snapshot.sh), outputs/parked*, other experiments' outputs (outputs/claude_*,
  outputs/aspire_*), scripts/tc1/ (except the commands named here), or docs/logs/. Brief the
  subagent with the same rule. Do not save memories.
- CLAUDE.md's "Self-Evolve"/"Log Everything" rules are suspended: do not read or write docs/logs/.
  The ONLY skill edits are your promotion step below.

Resuming (an earlier 6 h job may have ended mid-task)
- Look at $TASK_DIR first. fix_code.py and findings.md present: skip to promotion (if
  `record_skill_promotion.py verify` fails). Otherwise dispatch ONE new subagent with the template
  and tell it which iterations are already evaluated; it continues from there.

Promotion, after the subagent returns
- As in main-agent-prompt.md "6. Update skills": record_skill_promotion.py begin -> edit
  .claude/libero/skills/ from findings.md -> finish -> verify. If the library is empty or lacks
  the target file, create it (localize.md / grasp.md / transport.md / manipulation.md) with a
  one-line header and the pattern. If nothing is generalizable, finish with --reason (an empty
  update is a valid result; tell me).
- After verify passes, freeze the library:
    bash scripts/tc1/common/skills_snapshot.sh save {{TO}}
- Report: passes per iteration (iterations.md), which iteration is fix_code.py, the promoted
  patterns (one line each, file + section), the promotion patch path, and that {{TO}} was saved.

Never push to any remote. Start with the preflight report and wait for my go.

----- subagent template -----
You are a fix-loop subagent for ONE LIBERO-Pro task. Improve its program over at most 5
iterations on development seeds 51-65, then write fix_code.py and findings.md.

SUITE: {{SUITE}}
TASK:  {{TASK}}
GPU:   0
TASK_DIR=outputs/libero_fix_loop/{{SUITE}}/{{TASK}}
DEBUG_DIR=outputs/libero_fix_loop_debug/{{SUITE}}/{{TASK}}
Already evaluated: <iterations already evaluated, e.g. "iter_0 only">

Read first (paths relative to aspire/sim, the current directory):
- .claude/libero/fix-loop/subagent-prompt.md: sections "Context" (allowed / forbidden APIs),
  "Step 2" (reading trace.json), "Step 3" (replay_trial.py and the REPL) and "Step 5" (findings.md
  format). Its Stage 0 / Stage 1 structure and its 3-attempts-per-seed rule do NOT apply; the
  procedure below replaces them.
- .claude/libero/api-reference.md and every file in .claude/libero/skills/ (may be empty).
- $TASK_DIR/start_code.py and $TASK_DIR/iters/iter_0/ (the start program and its run on 51-65).

Iterations k = 1..5 (stop early at 15/15)
a. Base: the evaluated iteration with the most passes so far (ties: the later one).
b. Diagnose the base's failed seeds from its eval/trial_*/trace.json and summary.txt. You may run
   up to 8 single-seed replays or REPL sessions per iteration for keyframes and live inspection,
   with --args.output-dir under $DEBUG_DIR/iter_<k>/ and CUDA_VISIBLE_DEVICES=0.
c. Write ONE revised task-level program to $TASK_DIR/iters/iter_<k>/candidate_A/code.py (no
   seed-specific branches; localise at run time). python3 -m py_compile it.
d. Evaluate it on all 15 seeds, detached, then poll until iter_summary.json appears:
     IT=$TASK_DIR/iters/iter_<k>
     MUJOCO_GL=egl TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 setsid nohup .venv-libero/bin/python3 \
       scripts/libero/evosearch_eval.py --iter-dir $IT --suite {{SUITE}} --task {{TASK}} \
       --trials 15 --trial-seeds 51 52 53 54 55 56 57 58 59 60 61 62 63 64 65 \
       --sim-gpus 0 --parallel-per-gpu 4 --no-highlights > $IT/eval.log 2>&1 &
   If an iteration has code.py but no iter_summary.json (interrupted), rename its candidate_A/eval
   to eval_partial_<time> and re-run this command; never edit an evaluated iteration.
e. Append to $TASK_DIR/iterations.md: k, base iteration, the change in one line, passes/15,
   seeds that newly passed and newly failed versus the base.

After the iterations
- fix_code.py = a byte-identical copy (cp) of the evaluated iteration with the most passes
  (ties: fewer errors, then the earlier iteration). Copy it to $TASK_DIR/fix_code.py and to
  outputs/working_codes/{{SUITE}}_{{TASK}}_fix.py.
- Write $TASK_DIR/findings.md in the Step 5 format; evidence = the seeds an iteration flipped.

Never: seeds outside 51-65, run_fix_loop_validation.py, edits under .claude/libero/skills/,
reading outputs/ other than $TASK_DIR and $DEBUG_DIR, reading scripts/tc1/ or docs/, writing to
/tmp, saving memories, pushing.

Return in at most 8 lines: passes per iteration, which iteration is fix_code.py, the main failure
modes and what fixed them, fix_code.py and findings.md written yes/no.
