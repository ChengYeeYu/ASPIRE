# Task selection: which task should the next fix loop debug?

Build a skill library from nothing over 9 LIBERO-Pro tasks and compare two ways of choosing
the next task to debug:
- **disagreement**: an agent picks the task whose programs disagree most (`select_disagreement_prompt.md`).
- **top_down**: the first task not yet fixed, in the order below (the original ASPIRE way: work down the task table).

Tasks, in top-to-bottom order (`tsel.py` `TASKS`):

| # | Suite | Task |
|---|---|---|
| 1 | libero_goal_swap | open_the_middle_drawer_of_the_cabinet |
| 2 | libero_goal_swap | put_the_bowl_on_the_stove |
| 3 | libero_goal_swap | turn_on_the_stove |
| 4 | libero_spatial_swap | pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate |
| 5 | libero_spatial_swap | pick_up_the_black_bowl_next_to_the_ramekin_and_place_it_on_the_plate |
| 6 | libero_spatial_swap | pick_up_the_black_bowl_from_table_center_and_place_it_on_the_plate |
| 7 | libero_object_swap | pick_up_the_alphabet_soup_and_place_it_in_the_basket |
| 8 | libero_object_swap | pick_up_the_cream_cheese_and_place_it_in_the_basket |
| 9 | libero_object_swap | pick_up_the_salad_dressing_and_place_it_in_the_basket |

## Procedure (per arm)
1. **round_0** (shared by both arms): empty library L0 (`TS_L0_empty`, no skill files at all).
   3 zero-shot programs per task, each run on seeds 51-65.
2. For n = 1..3:
   - **select**: the arm's rule picks one task not fixed yet, from the previous round's results.
   - **fix**: fix loop on that task, starting from its best program of the previous round (most
     passes, then fewer crashes), at most 5 iterations on 51-65 (`fix_prompt.md`). Skills are
     promoted, and the library is saved as `TS_L<n>_<arm>`.
   - **round_n**: 3 fresh programs from L_n for every task not fixed yet, run on 51-65.
3. **report**: per task, mean success of one fresh program in each round, and the paired change
   between rounds on the tasks that were measured in both.

The model is whatever the session runs (Sonnet 5 via `/model`). No subagent model override anywhere.

## Running it
Same session setup as the other experiments: `git pull` on TC1, `sbatch scripts/tc1/setup/04_session.sh`,
Jupyter terminal in `~/ASPIRE/aspire/sim` with the env block (`ASPIRE_ROOT`, `MUJOCO_GL=egl`,
`TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1`). The driver says what to run next, with the exact command:
```bash
.venv/bin/python3 scripts/tc1/task_selection/tsel.py next --arm top_down        # or --arm disagreement
```
Run what it prints, then ask again. Every step can be resumed: if a 6 h job ends, start a new
session and run `next` again. The steps, in order:

| Step | Command (as printed by `next`) | Time |
|---|---|---|
| init (once) | `tsel.py init`: manifest, checks the 9 task names against the installed suites | seconds |
| probe (once) | `libgen.py probe`: one scripted scene probe per task on seed 100 | ~1-2 min/task |
| empty library (once) | `skills_snapshot.sh save-empty TS_L0_empty` | - |
| phase start | `skills_snapshot.sh restore <snap>` + `libgen.py phase-start` | - |
| codegen | `claude "$(sed ... libgen_codegen_prompt.md)"`: one subagent per program | ~30 min |
| eval | `libgen.py eval`, detached | 9 tasks: 405 trials, ~2 h at 4 workers |
| summarize | `libgen.py summarize` | - |
| select | `tsel.py select`; for disagreement also the `claude` selection command it prints, then `select` again to validate | minutes |
| fix-begin | `tsel.py fix-begin`: restores the arm's library, parks `outputs/libero_fix_loop*` + `working_codes`, sets up iter_0 | - |
| fix loop | `claude "$(sed ... fix_prompt.md)"`: one subagent, at most 5 iterations | ~1-3 h |
| fix-end | `tsel.py fix-end`: checks promotion + snapshot, moves the outputs to `ROOT/<arm>/fix_<n>/`, un-parks | - |

`ROOT=outputs/task_selection`. Budget for both arms with 3 rounds each: 405 + 2 x (8+7+6) x 45 = 2295 trials
(~11 h eval), plus 6 fix loops and 7 codegen sessions.

Run the arms one after the other, never together: they share `.claude/libero/skills/`.
`round_0` is done once; the second arm's `next` goes straight to its first `select`.

Restoring `TS_L0_empty` deletes the committed skill files from the working tree (git shows them as
deleted). This is expected. `bash scripts/tc1/common/skills_snapshot.sh restore L0_clean` (or
`git checkout -- .claude/libero/skills`) brings them back after the experiment.

## Report
```bash
.venv/bin/python3 scripts/tc1/task_selection/tsel.py report          # both arms; writes ROOT/<arm>/report.json
```
- per task: mean success in round 0..3 (blank once the task is fixed), and the round it was fixed in
- per fix: the task, its start rate and the dev rate of its fix_code.py (51-65, the seeds it was debugged on)
- per round: paired delta = mean change on tasks measured in both rounds n-1 and n (main number);
  mean over the unfixed tasks (it also moves because the fixed task drops out); and
  `mean_rate_all_with_fixed` in report.json (fixed tasks counted at their fix_code dev rate)

## Rules and caveats
- Nothing may edit `.claude/libero/skills/` during codegen or eval (`libgen.py eval` refuses if the
  library changed since phase-start).
- Measurement and fix loop use the same seeds (51-65). That is acceptable because a task is never
  measured again after its fix loop, but there is no held-out score.
- 3 programs x 15 seeds is a noisy rate (earlier repeats of the same run differed a lot). If time
  allows, repeat round_0 as a second phase on the same empty library to see how much the numbers
  move with no library change.
- The disagreement agent may read the previous round's programs and traces for the unfixed tasks,
  and nothing else. Its `select.json` lists the files it opened.
