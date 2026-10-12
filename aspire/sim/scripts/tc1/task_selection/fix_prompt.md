Run a LIBERO fix loop on ONE task to grow the shared skill library, for the task-selection
experiment (arm {{ARM}}, step {{N}}). It follows .claude/libero/fix-loop/ (main-agent-prompt.md
"6. Update skills" for promotion, subagent-prompt.md for tools and findings.md), with the approved
deviations below; do not stop on them in preflight.

This run is unattended (overnight, 6 h SLURM job). Nobody will answer questions. Work through the
steps below to the end without waiting for me, except where a step says STOP.

==================================================================================================
0. Paths and placeholders
==================================================================================================
- Working directory: aspire/sim (all paths below are relative to it).
- SUITE={{SUITE}}  TASK={{TASK}}
- TASK_DIR=outputs/libero_fix_loop/{{SUITE}}/{{TASK}}
- DEBUG_DIR=outputs/libero_fix_loop_debug/{{SUITE}}/{{TASK}}
- Start library = snapshot {{FROM}} (it may be EMPTY: no skill files at all). End library = {{TO}}.
- The task does not start from scratch: $TASK_DIR/start_code.py is the best of 3 zero-shot
  programs for this task, and $TASK_DIR/iters/iter_0/ holds it (candidate_A/code.py) with its
  run on seeds 51-65 (iter_summary.json, candidate_A/eval/trial_*/{trace.json,summary.txt};
  no keyframes). iter_0 is already evaluated: never re-run it.
- Development seeds 51-65 only. No Stage 2, no seeds 1-50. gen_progress.py may list other
  pending tasks -- ignore them.

==================================================================================================
1. Waiting rules (coordinator AND subagent) -- the most important section
==================================================================================================
A subagent that ends its turn is treated as finished and handed back, even if it meant to wait
for a notification. A previous run lost its subagent this way mid-iteration. Therefore:

- NEVER end your turn while an eval, replay, test or monitor of yours is still running.
  Do not write "I'll wait for the notification" and stop. Do not issue filler calls
  (`echo idle`, `true`, `sleep 1`). A bare `sleep N` is blocked by the harness.
- Wait INSIDE a tool call. For an eval:
      python3 scripts/tc1/common/wait_eval.py $IT          # Bash timeout: 600000
  exit 0 = DONE (iter_summary.json exists), 1 = still RUNNING (call it again, as often as needed),
  3 = DIED (no eval process and no summary: rename candidate_A/eval to eval_partial_<time>
  and re-launch the eval). For any other detached process:
      python3 scripts/tc1/common/wait_eval.py --pid <PID>   # Bash timeout: 600000
- Give every Bash call that runs the simulator an explicit timeout of 600000 ms (the default is
  120 s; longer commands get moved to the background, which then forces waiting).
- A single-seed replay or REPL script takes ~1.5 min: run it in the foreground with timeout
  600000. Up to 4 seeds in one call is fine in the foreground. Anything that may exceed 9 min:
  run it detached (`setsid nohup ... > log 2>&1 & echo $!`) and wait with `wait_eval.py --pid`.
- Do not use the Monitor tool or run_in_background for waiting.
- The ONLY time the subagent may end its run is the final SubagentHandback (see section 5,
  "Return"), after fix_code.py and findings.md are written, or on an unrecoverable error.

==================================================================================================
2. Isolation (the library update must come from this task's own evidence only)
==================================================================================================
Never open, list, search, diff or `git show` any of these (and brief the subagent with the same
rules):
- outputs/task_selection/, outputs/libgen*, outputs/skill_snapshots/ (only via
  skills_snapshot.sh), outputs/parked*, outputs/claude_*, outputs/aspire_*, docs/logs/,
  scripts/tc1/ (except the exact commands named in this prompt).
- Any OTHER version of the skill library: no `git log`, `git show`, `git diff`, `git blame`,
  `git stash`, `git checkout` or `git restore` on .claude/libero/skills/, and no reading of
  skills from any commit, branch or snapshot. The library is what is on disk now, nothing else
  (it is meant to be empty or small in this experiment).
- No memories (do not save or read Claude memories).
- CLAUDE.md's "Self-Evolve"/"Log Everything" rules are suspended: do not read or write
  docs/logs/. The ONLY skill edits are the coordinator's promotion step (section 4).

Files and scratch:
- /tmp is wiped when the job ends. Write NOTHING to /tmp -- this includes the Claude scratchpad
  directory (/tmp/claude-*). Scratch scripts, REPL scripts, logs and replay outputs go under
  $DEBUG_DIR/ (e.g. $DEBUG_DIR/scratch/, $DEBUG_DIR/iter_<k>/).
- Never push to any remote. No git commits.

==================================================================================================
3. Coordinator (you): preflight, dispatch, supervise
==================================================================================================
3a. Preflight. Check and print:
    bash scripts/tc1/common/skills_snapshot.sh check {{FROM}}          -> must print OK
    ls $TASK_DIR $TASK_DIR/iters                                        -> start_code.py, iters/
    for p in 8114 8115 8116; do curl -s -o /dev/null -w "$p %{http_code}\n" --max-time 3 http://127.0.0.1:$p/health; done
                                                                        -> perception servers up (any HTTP code, not 000)
    nvidia-smi --query-gpu=memory.used,memory.total --format=csv
    State of the task:
      - fresh: $TASK_DIR has only start_code.py and iters/iter_0; outputs/libero_fix_loop_debug
        and outputs/working_codes absent.
      - resuming: later iters/iter_<k>/, iterations.md, notes.md and/or $DEBUG_DIR exist from an
        earlier job. List which iterations have iter_summary.json (evaluated) and which have only
        code.py (interrupted).
      - done: fix_code.py and findings.md exist -> skip to 4 (promotion), unless
        `.venv/bin/python3 scripts/libero/record_skill_promotion.py verify --suite {{SUITE}} --task {{TASK}}`
        already passes and snapshot {{TO}} exists -> skip to 4d (report).
    If the snapshot check fails, a server is down (000), or the state matches none of the above:
    STOP and report. Otherwise print the preflight report and CONTINUE without waiting for me.

3b. Dispatch exactly ONE subagent (Agent tool, general-purpose, NO model override), briefed with
    the template in section 5, placeholders filled, nothing task-specific added. In
    "Already evaluated" list the evaluated iterations with their passes (e.g. "iter_0 0/15" or
    "iter_0 0/15, iter_1 4/15; iter_2 has code.py but no summary (interrupted)").

3c. Supervise. When the subagent returns, check on disk (not just its message):
      ls $TASK_DIR $TASK_DIR/iters; cat $TASK_DIR/iterations.md
    - fix_code.py AND findings.md present -> go to 4.
    - Otherwise it stopped early. Do NOT give up and do NOT ask me. Find out what is in flight:
        python3 scripts/tc1/common/wait_eval.py $TASK_DIR/iters/iter_<k> --max-wait 5   # Bash timeout: 600000
      for the newest iteration (exit 1 = eval still running, 0 = done, 3 = died). Then RESUME THE
      SAME SUBAGENT with SendMessage (its agent id/name), with: what is on disk, which evals are
      done/running/died, "continue from where you stopped; follow section 1 waiting rules: never
      end your turn while something runs, wait with wait_eval.py", and the remaining iteration
      budget. Repeat this as often as needed (up to 6 resumes).
    - Only if SendMessage to that subagent is impossible (error / unknown agent): dispatch ONE
      new subagent with the same template; "Already evaluated" must list the state on disk and
      tell it to read $TASK_DIR/notes.md and iterations.md first. Count it as a restart and
      mention it in the report.
    - While the subagent works, do nothing else: no edits, no evals, no reading of its files
      beyond the checks above.

==================================================================================================
4. Coordinator: promotion, snapshot, report
==================================================================================================
4a. Check before promoting: fix_code.py is byte-identical to the chosen iteration's
    candidate_A/code.py (`cmp`), and outputs/working_codes/{{SUITE}}_{{TASK}}_fix.py exists.
    If not, fix the copy yourself (cp from the iteration the template's rule picks).
4b. Promotion as in main-agent-prompt.md "6. Update skills":
    record_skill_promotion.py begin -> edit .claude/libero/skills/ from findings.md -> finish ->
    verify. If the library is empty or lacks the target file, create it (localize.md / grasp.md /
    transport.md / manipulation.md) with a one-line header and the pattern. Promote general
    patterns only: no seed numbers, no constants fitted on one seed, no task-specific object
    names unless the pattern is about that object class. If nothing is generalizable, finish with
    --reason (an empty update is a valid result; say so in the report).
4c. After verify passes, freeze the library:
      bash scripts/tc1/common/skills_snapshot.sh save {{TO}}
4d. Report (final message): passes per iteration (iterations.md), which iteration is
    fix_code.py, the promoted patterns (one line each, file + section), the promotion patch path,
    that {{TO}} was saved, and how many times the subagent stopped early and was resumed.

==================================================================================================
5. Subagent template (fill the placeholders, add nothing task-specific)
==================================================================================================
----- subagent template -----
You are a fix-loop subagent for ONE LIBERO-Pro task. Improve its program over at most 5
iterations on development seeds 51-65, then write fix_code.py and findings.md. You run
unattended: nobody answers questions. Work until the end in one run.

SUITE: {{SUITE}}
TASK:  {{TASK}}
GPU:   0
TASK_DIR=outputs/libero_fix_loop/{{SUITE}}/{{TASK}}
DEBUG_DIR=outputs/libero_fix_loop_debug/{{SUITE}}/{{TASK}}
Already evaluated: <iterations already evaluated with passes, and any interrupted iteration>

RULE 1 -- never stop while something runs. If you end your turn, your run is over and your
work is lost. Never end your turn while an eval, replay or test is running. Never write "I'll
wait for the notification". No filler calls (echo idle, true, sleep 1); a bare sleep is blocked.
Wait inside ONE Bash call (timeout 600000):
    python3 scripts/tc1/common/wait_eval.py $IT        # 0 DONE, 1 RUNNING -> call again, 3 DIED -> re-launch
    python3 scripts/tc1/common/wait_eval.py --pid PID  # any detached process
Give every simulator Bash call timeout 600000. Single-seed replays/REPL scripts (~1.5 min) and
up to 4 seeds run in the foreground; longer jobs detached (`setsid nohup ... & echo $!`) +
wait_eval.py --pid. Do not use Monitor or run_in_background. The run ends ONLY with
SubagentHandback after fix_code.py and findings.md are written (or an unrecoverable error).

RULE 2 -- isolation. Read only: .claude/libero/fix-loop/subagent-prompt.md,
.claude/libero/api-reference.md, .claude/libero/skills/ (as on disk now, may be empty),
cap/ and scripts/libero/ source, $TASK_DIR, $DEBUG_DIR. Never read other outputs/ dirs,
scripts/tc1/ (except running scripts/tc1/common/wait_eval.py), docs/, or any other version of
the skill library (no git log/show/diff/blame/stash/checkout on .claude/libero/skills/, no
other commits or branches). Never edit .claude/libero/skills/. No memories. No git commits,
no push. Seeds 51-65 only; never run_fix_loop_validation.py.

RULE 3 -- files. Write NOTHING to /tmp (including the Claude scratchpad /tmp/claude-*): it is
wiped when the job ends. Scratch scripts, REPL scripts, logs and replay outputs go under
$DEBUG_DIR/scratch/ and $DEBUG_DIR/iter_<k>/.

RULE 4 -- keep your context small (you must last 5 iterations). Never cat a whole trace.json
or a long log: extract what you need with python/grep and print at most ~60 lines per call
(use head/tail). Do not re-read files you already read unless they changed.

RULE 5 -- keep notes for resumption. After each step, update $TASK_DIR/notes.md (short):
current iteration, base iteration, current hypothesis, what was tried in replays and what it
showed, next step. If you are resumed or replaced, read notes.md and iterations.md first and
continue from there; never redo an evaluated iteration.

Read first (paths relative to aspire/sim, the current directory):
- .claude/libero/fix-loop/subagent-prompt.md: sections "Context" (allowed / forbidden APIs),
  "Step 2" (reading trace.json), "Step 3" (replay_trial.py and the REPL) and "Step 5" (findings.md
  format). Its Stage 0 / Stage 1 structure and its 3-attempts-per-seed rule do NOT apply; the
  procedure below replaces them.
- .claude/libero/api-reference.md and every file in .claude/libero/skills/ (may be empty).
- $TASK_DIR/start_code.py and $TASK_DIR/iters/iter_0/ (the start program and its run on 51-65).
- If present: $TASK_DIR/notes.md and $TASK_DIR/iterations.md (you are resuming).

Iterations k = 1..5 (stop early at 15/15)
a. Base: the evaluated iteration with the most passes so far (ties: the later one).
b. Diagnose the base's failed seeds from its eval/trial_*/trace.json and summary.txt. You may run
   up to 8 single-seed replays or REPL sessions per iteration for keyframes and live inspection,
   with --args.output-dir under $DEBUG_DIR/iter_<k>/ and CUDA_VISIBLE_DEVICES=0.
c. Write ONE revised task-level program to $TASK_DIR/iters/iter_<k>/candidate_A/code.py (no
   seed-specific branches; localise at run time). python3 -m py_compile it.
d. Evaluate it on all 15 seeds, detached, then wait for it with wait_eval.py (RULE 1):
     IT=$TASK_DIR/iters/iter_<k>
     MUJOCO_GL=egl TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 setsid nohup .venv-libero/bin/python3 \
       scripts/libero/evosearch_eval.py --iter-dir $IT --suite {{SUITE}} --task {{TASK}} \
       --trials 15 --trial-seeds 51 52 53 54 55 56 57 58 59 60 61 62 63 64 65 \
       --sim-gpus 0 --parallel-per-gpu 4 --no-highlights > $IT/eval.log 2>&1 &
     python3 scripts/tc1/common/wait_eval.py $IT       # Bash timeout 600000; repeat while exit 1
   An eval takes ~10-20 min, so expect 2-3 wait calls. While waiting you may NOT do anything
   that uses the GPU; reading the code or the base's traces is fine between wait calls.
   If an iteration has code.py but no iter_summary.json (interrupted) and wait_eval.py says
   DIED, rename its candidate_A/eval to eval_partial_<time> and re-run the eval command; never
   edit an evaluated iteration.
e. Append to $TASK_DIR/iterations.md: k, base iteration, the change in one line, passes/15,
   seeds that newly passed and newly failed versus the base. Update notes.md.

After the iterations
- fix_code.py = a byte-identical copy (cp) of the evaluated iteration with the most passes
  (ties: fewer errors, then the earlier iteration). Copy it to $TASK_DIR/fix_code.py and to
  outputs/working_codes/{{SUITE}}_{{TASK}}_fix.py (mkdir -p outputs/working_codes).
- Write $TASK_DIR/findings.md in the Step 5 format; evidence = the seeds an iteration flipped.

Return (SubagentHandback, only now) in at most 8 lines: passes per iteration, which iteration is
fix_code.py, the main failure modes and what fixed them, fix_code.py and findings.md written
yes/no.
----- end of subagent template -----
