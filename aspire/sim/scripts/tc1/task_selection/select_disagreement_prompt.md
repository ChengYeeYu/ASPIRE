Choose ONE task to debug next, for building a shared robot skill library (arm "disagreement",
step {{ROUND}}).

Setting: a skill library is built task by task. At each step one task gets a fix loop -- an agent
debugs that task's best program on seeds 51-65 and promotes what it learned into the library --
and then fresh programs are written zero-shot for all other unfixed tasks using the updated
library. You choose the task for the next fix loop. The goal is the task whose debugging will
most improve the library for the OTHER tasks.

The rule under test is DISAGREEMENT: prefer the task whose programs disagree most. The idea is
that where some programs (or some seeds) succeed and others fail, the task sits at the edge of
what the library can do, and a fix loop gets contrasting evidence to learn from. A task where
every program passes everywhere, or every program fails everywhere, shows no disagreement.

Input: {{INPUT}}
For each unfixed task (id <suite>/<task>), K programs were written from the current library and
each was run once on the same seeds ("seeds"):
- pass_matrix: per program, one character per seed in "seeds" order, 1 = pass, 0 = fail
- rates: each program's success rate; mean_rate: their mean; best_rate: the best program
- any_pass_rate: share of seeds solved by at least one program
- seed_disagreement: share of seeds where some programs pass and some fail
- errors: trials where the program crashed

You may also open, for the tasks in the input only, files under <programs_dir>/<task id>/candidate_<X>/:
code.py (the program) and eval/trial_*/summary.txt and eval/trial_*/trace.json (one run per seed;
the directory name ends in taskcompleted_1 for a pass). Use them to judge whether programs take
different approaches or fail at different stages. Open no other file and run nothing except
writing the output.

Decide
1. Define your disagreement score: which signals you combine (outcome disagreement across
   seeds, spread between programs, differences in approach or failure stage) and how. State it
   so someone else could recompute the outcome part from the input.
2. Score every task in the input. Choose the highest. For ties or near-ties say what broke them.

Write {{OUT}} and nothing else:
{
  "arm": "disagreement",
  "round": {{ROUND}},
  "chosen_task": "<task id exactly as in the input>",
  "runner_up": "<task id>",
  "score_definition": "<how you scored disagreement>",
  "scores": {"<task id>": <number>, "...": 0},
  "files_opened": ["<files you opened besides the input, or empty>"],
  "reasoning": "<3-6 sentences, citing the numbers>"
}
Then print the file and stop.

Rules: do not edit any other file, do not read scripts/tc1/, docs/, .claude/libero/skills/ or other
outputs/ paths, do not save memories, never push to any remote.
