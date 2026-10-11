Run the LIBERO fix loop per .claude/libero/fix-loop/QUICKSTART.md with these approved deviations
(do not stop on them in preflight):

Scope
- ONE task only: SUITE=libero_goal_swap TASK=put_the_bowl_on_the_stove.
  gen_progress.py will list other pending tasks — ignore them, never dispatch or evaluate them.

Hardware (NTU TC1, SLURM job, 6 h wall limit)
- Single V100 = GPU 0. SAM3/GraspNet/PyRoKi already run on it (ports 8114-8116). The Stage 1
  worker and the Stage 2 eval also use GPU 0. Never start/stop the servers.
- /tmp is wiped when the job ends: keep all scratch code and replay outputs under outputs/
  (e.g. $TASK_DIR/attempts/, outputs/libero_fix_loop_debug/) instead of /tmp.

Subagents
- Exactly ONE Stage 1 subagent in total, for this task, on GPU 0. Fill the subagent-prompt.md
  template with GPU: 0 and add the /tmp rule above to it.
- Do not spawn any other agents (no Explore/Plan/helper agents) — read the runbooks yourself.
- If the subagent returns without fix_code.py or findings.md, do NOT re-dispatch; tell me and wait.

Resuming (an earlier 6 h job may have ended mid-task)
- Regenerate progress first and check outputs/libero_fix_loop/libero_goal_swap/put_the_bowl_on_the_stove/.
- Stage 1 files but no fix_code.py: resume in ONE new subagent that reads those files first.
- fix_code.py present: skip Stage 1; do skill promotion if `record_skill_promotion.py verify` fails,
  then Stage 2 with --resume (finished seeds are skipped).
- Never redo a finished stage.

Then, as in main-agent-prompt.md: skill promotion (begin → edit skills → finish → verify),
Stage 2 on seeds 1-50 with --resume in the background on GPU 0, regenerate progress, and report
per the Completion Report — for this one task.

Never push to any remote. Start with the preflight report and wait for my go.
