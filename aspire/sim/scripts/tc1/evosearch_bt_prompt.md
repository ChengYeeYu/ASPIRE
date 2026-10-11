Run the EVOSEARCH-BT arm, repetition {{REP}}, of a controlled comparison: original ASPIRE Evolutionary
Search with agent-chosen parents, where every new candidate is written as a BEHAVIOUR TREE with a check
on every action node, for ONE task.

Read scripts/tc1/evosearch_agent_prompt.md and follow ALL of it (which in turn follows
scripts/tc1/evosearch_prompt.md: fixed inputs, frozen settings, hardware, frozen skill library,
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

2. Behaviour-tree candidates (the only change to how candidates are written)
   - iter_00/candidate_A stays START_CODE verbatim (the baseline; exempt). EVERY other candidate
     (iter_00 B-H and all candidates of iter_01+) is a behaviour tree built on scripts/tc1/bt_lib.py:
     * paste the block from "# ===== BT_LIB BEGIN" to "# ===== BT_LIB END =====" VERBATIM at the top
       of code.py (read the file; its docstrings are the API). Never edit scripts/tc1/bt_lib.py or the
       pasted block; put your own helpers and checks outside it.
     * build the task as a tree of Sequence / Fallback / Retry / Action / Condition / Do nodes, and run
       it with run_tree(root) as the only entry point. No motion outside the tree, and no "proceed
       anyway": when a subtree has no options left, the tree returns FAILURE.
     * all motion goes through bt_move / bt_move_pose / bt_open / bt_close inside an Action's act
       (raw move_to_joints / open_gripper / close_gripper / goto_home_joint_position are not allowed).
   - EVERY Action has a check that tests that action's own effect from observations, using allowed
     APIs only. The library gives the minimum checks: joints_reached(target) for moves (joint space;
     note robot_cartesian_pos is in the robot-base frame, not world), gripper_is_open() after opening,
     gripper_holding() after closing. You design the task-specific checks on top (e.g. the object
     came up with the gripper after a lift, the gripper is still holding before release, the arm is
     over the target region before opening); a constant check (lambda bb: True) is not allowed.
   - Budgets are part of the design: the episode has 4000 sim steps (bt_lib counts ~120 per move,
     30 per gripper action) and evosearch_eval kills a trial at 180 s wall clock (bt_lib stops new
     tries at 160 s). A SAM3 call takes ~2 s, so perception checks are not free.
   - The candidate's strategy (grasp choice, prompts, heights, which retries/fallbacks) is still
     yours to evolve as in the runbook; the tree structure and per-action checks are the fixed form.

3. Gates (in addition to the agent arm's)
   - BEFORE launching every round's eval:
       .venv/bin/python3 scripts/tc1/bt_check.py verify --iter-dir $RUN_DIR/iter_NN
     must print OK (it skips iter_00/candidate_A). Fix the candidates until it does.
   - AFTER every round's eval:
       .venv/bin/python3 scripts/tc1/bt_check.py report --iter-dir $RUN_DIR/iter_NN
     and paste its output into findings.md for that round; use it in diagnosis (which node fails,
     how often, for which candidates) alongside the traces.
   - The final code must pass bt_check.py verify, unless it is the START_CODE fallback.
   - After Stage 2:
       .venv/bin/python3 scripts/tc1/bt_check.py report --logs $EVALDIR/libero_goal_swap/put_the_bowl_on_the_stove/runs/<run_id>/logs
   - scripts/tc1/bt_lib.py and bt_check.py are frozen like the skill library: nobody edits them.

4. Brief the subagent with sections 2 and 3 VERBATIM (they replace nothing in the runbook; they add
   the required code form and gates).

5. Final report additions: per round, the bt_check report's top failing nodes; Stage 2's report; and
   whether the final code's tree ever returned FAILURE early (instead of carrying on) on held-out.
