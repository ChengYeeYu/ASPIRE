Run the LIBERO fix loop per .claude/libero/fix-loop/QUICKSTART.md on ONE task, to produce the
library update L1 for the library-gain measurement, arm {{ARM}}. Approved deviations below; do not
stop on them in preflight.

Scope
- ONE task only: SUITE=libero_goal_swap TASK={{TASK}}.
  gen_progress.py will list other pending tasks -- ignore them, never dispatch or evaluate them.
- Start library = snapshot L0_clean. Preflight must show
    bash scripts/tc1/common/skills_snapshot.sh check L0_clean   -> OK
  and outputs/libero_fix_loop, outputs/libero_fix_loop_debug, outputs/working_codes absent
  (they were moved aside before this session). If either fails, report and stop.
- Development seeds 51-65 only. NO Stage 2: the held-out score of this task is not used.

Hardware (NTU TC1, SLURM job, 6 h wall limit)
- Single V100 = GPU 0. SAM3/GraspNet/PyRoKi already run on it (ports 8114-8116). The Stage 1
  worker also uses GPU 0. Never start/stop the servers.
- /tmp is wiped when the job ends: keep all scratch code and replay outputs under outputs/
  (e.g. $TASK_DIR/attempts/, outputs/libero_fix_loop_debug/) instead of /tmp.

Subagents
- Exactly ONE Stage 1 subagent in total, for this task, on GPU 0, with NO model override. Fill the
  subagent-prompt.md template with GPU: 0 and add the /tmp rule and the isolation rules below to it.
- Do not spawn any other agents (no Explore/Plan/helper agents) -- read the runbooks yourself.
- If the subagent returns without fix_code.py or findings.md, do NOT re-dispatch; tell me and wait.

Isolation (L1 must come from this task's own Stage 1 evidence only)
- Never open, list or search outputs/libgen*, outputs/skill_snapshots/ (only via skills_snapshot.sh), outputs/parked*, other
  experiments' outputs (outputs/claude_*, outputs/aspire_*), scripts/tc1/ (except the commands
  named here), or docs/logs/. Brief the subagent with the same rule. Do not save memories.
- CLAUDE.md's "Self-Evolve"/"Log Everything" rules are suspended: do not read or write docs/logs/.
  The ONLY skill edits are the coordinator's promotion step below.

Resuming (an earlier 6 h job may have ended mid-task)
- Regenerate progress first and check outputs/libero_fix_loop/libero_goal_swap/{{TASK}}/.
- Stage 1 files but no fix_code.py: resume in ONE new subagent that reads those files first.
- fix_code.py present: skip Stage 1; do skill promotion if `record_skill_promotion.py verify` fails.
- Never redo a finished stage.

Then, as in main-agent-prompt.md "6. Update skills": record_skill_promotion.py begin -> edit
.claude/libero/skills/ from findings.md (generalizable patterns, provenance included) -> finish ->
verify. If nothing is generalizable, finish with --reason (an empty L1 is a valid result; tell me).
After verify passes, freeze the library:
    bash scripts/tc1/common/skills_snapshot.sh save L1_{{ARM}}
Report: Stage 1 development successes on 51-65, fix_code.py and findings.md paths, the promoted
patterns (one line each, file + section), the promotion patch path, and that L1_{{ARM}} was saved.

Never push to any remote. Start with the preflight report and wait for my go.
