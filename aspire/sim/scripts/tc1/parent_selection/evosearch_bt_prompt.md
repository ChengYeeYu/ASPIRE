Run the EVOSEARCH-BT arm, repetition {{REP}}, of a controlled comparison: original ASPIRE Evolutionary
Search with agent-chosen parents, where every new candidate is written as a BEHAVIOUR TREE with a check
on every action node, for ONE task.

Read scripts/tc1/parent_selection/evosearch_agent_prompt.md and follow ALL of it (which in turn follows
scripts/tc1/parent_selection/evosearch_prompt.md: fixed inputs, frozen settings, hardware, frozen skill library,
isolation, agents, Stage 2, resuming, final report, agent-chosen parents and final pick,
--parallel-per-gpu 4), treating every {{REP}} in them as {{REP}}, with exactly these substitutions
and additions and nothing else changed:

1. Output roots (replaces section 1 of evosearch_agent_prompt.md)
   - EVOSEARCH_DIR = outputs/claude_evosearch_bt_r{{REP}}
   - EVALDIR       = outputs/aspire_evosearch_bt_eval_r{{REP}}
   (also in the Stage 2 command: --fix-code outputs/claude_evosearch_bt_r{{REP}}/.../evosearch_best_code.py
    --output-dir outputs/aspire_evosearch_bt_eval_r{{REP}})
   Isolation also covers outputs/claude_evosearch_agent_r*, outputs/claude_evosearch_bt_r* and their
   eval roots, other than this run's own two roots.
   parents.json uses "selection": "agent" as in the agent arm.
   Never open scripts/tc1/parent_selection/EXPERIMENT.md or FINDINGS.md, scripts/tc1/setup/TC1_NOTES.md,
   scripts/tc1/README.md, or anything in scripts/tc1/library_gain/ (they describe other runs);
   brief the subagent with the same rule.

2. Behaviour-tree candidates (the only change to how candidates are written)
   - iter_00/candidate_A stays START_CODE verbatim (the baseline; exempt). EVERY other candidate
     (iter_00 B-H and all candidates of iter_01+) is a behaviour tree built on scripts/tc1/parent_selection/bt_lib.py:
     * paste the block from "# ===== BT_LIB BEGIN" to "# ===== BT_LIB END =====" VERBATIM at the top
       of code.py (read the file; its docstrings are the API). Never edit scripts/tc1/parent_selection/bt_lib.py or the
       pasted block; put your own helpers and checks outside it.
     * build the task as a tree of Sequence / Fallback / Retry / Action / Condition / Do nodes, and run
       it with run_tree(root) as the only entry point. No motion outside the tree: when the tree
       returns FAILURE, the code ends.
     * all motion goes through bt_move / bt_move_pose / bt_open / bt_close inside an Action's act
       (raw move_to_joints / open_gripper / close_gripper / goto_home_joint_position are not allowed).
   - EVERY Action has a check that tests that action's own effect, using allowed APIs only. You
     write the checks; the library provides none. A constant check (lambda bb: True) is not allowed.
   - Limits: the episode has 4000 sim steps (bt_lib counts 120 per move, 30 per gripper action) and
     evosearch_eval kills a trial at 180 s wall clock (bt_lib starts no new try after 160 s).
   - The strategy is yours to evolve as in the runbook; the tree structure and per-action checks
     are the fixed form.

3. Gates (in addition to the agent arm's)
   - BEFORE launching every round's eval:
       .venv/bin/python3 scripts/tc1/parent_selection/bt_check.py verify --iter-dir $RUN_DIR/iter_NN
     must print OK (it skips iter_00/candidate_A). Fix the candidates until it does.
   - AFTER every round's eval:
       .venv/bin/python3 scripts/tc1/parent_selection/bt_check.py report --iter-dir $RUN_DIR/iter_NN
     and paste its output into findings.md for that round.
   - The final code must pass bt_check.py verify, unless it is the START_CODE fallback.
   - After Stage 2:
       .venv/bin/python3 scripts/tc1/parent_selection/bt_check.py report --logs $EVALDIR/libero_goal_swap/put_the_bowl_on_the_stove/runs/<run_id>/logs
   - scripts/tc1/parent_selection/bt_lib.py and bt_check.py are frozen like the skill library: nobody edits them.

4. Brief the subagent with sections 2 and 3 VERBATIM (they replace nothing in the runbook; they add
   the required code form and gates).

5. Final report additions: per round, the bt_check report; and Stage 2's bt_check report.
