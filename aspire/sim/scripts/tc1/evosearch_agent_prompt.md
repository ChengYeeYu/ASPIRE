Run the EVOSEARCH-AGENT-PARENTS arm, repetition {{REP}}, of a controlled comparison: original ASPIRE
Evolutionary Search, where the agent chooses each round's parents itself (as in upstream ASPIRE and
evosearch r1), for ONE task.

Read scripts/tc1/evosearch_prompt.md and follow ALL of it (fixed inputs, frozen settings, hardware,
frozen skill library, isolation, agents, Stage 2, resuming, final report), treating every {{REP}} in it
as {{REP}}, with exactly these substitutions and nothing else changed:

1. Output roots
   - EVOSEARCH_DIR = outputs/claude_evosearch_agent_r{{REP}}
   - EVALDIR       = outputs/aspire_evosearch_agent_eval_r{{REP}}
   (also in the Stage 2 command: --fix-code outputs/claude_evosearch_agent_r{{REP}}/.../evosearch_best_code.py
    --output-dir outputs/aspire_evosearch_agent_eval_r{{REP}})
   Isolation also covers outputs/claude_evosearch_agent_r* and outputs/aspire_evosearch_agent_eval_r*
   other than this run's own two roots.
2. Parent selection is NOT done by a script. Drop the "Parent selection is done by a SCRIPT" bullet:
   never run select_parents.py select or verify. The subagent follows the runbook as written
   (subagent-prompt.md Step 6 item 3, "seeded from top-3 survivors of the current iteration"),
   choosing parents by its own judgment from the leaderboard. Still record its choice: for every
   round N >= 1 write $RUN_DIR/iter_NN/parents.json BEFORE launching that round's eval, same format
   with "selection": "agent", and one line per candidate in findings.md on why those parents.
3. Final code is chosen as in the runbook (subagent-prompt.md Step 7a: the subagent's pick from the
   final leaderboard + the fallback check), NOT by select_parents.py best. After Stage 1, run
     .venv/bin/python3 scripts/tc1/select_parents.py best --run-dir $RUN_DIR
   for the record only (it writes best.json; do not use it to change evosearch_best_code.py), and
   report both picks.
4. In the resuming rules: when continuing a RUN_DIR, the new subagent chooses parents from the last
   complete round's leaderboard as in 2.

Same model, K, seeds 51-65, stop rules, evosearch_eval.py flags, detached evals, single subagent.

Skill library stays FROZEN at the after_fixloop snapshot (unchanged from evosearch_prompt.md; the agent
choosing parents does NOT extend to skills): nobody edits .claude/libero/skills/, patterns go into
findings.md only, and the subagent brief says so. Run
  bash scripts/tc1/skills_snapshot.sh check after_fixloop
in preflight (do not start if it is not OK), after every round's eval, and in the final report.
