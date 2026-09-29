Run the DISAGREEMENT-SELECTION arm, repetition {{REP}}, of a controlled comparison against
Evolutionary Search, for ONE task.

GUARD: if the "Parent selection rule" section below still contains the word TODO, do nothing else:
report "disagreement selection not implemented yet" and stop.

Read scripts/tc1/evosearch_prompt.md and follow ALL of it (fixed inputs, frozen settings, hardware,
frozen skill library, agents, Stage 2, resuming, final report), treating every {{REP}} in it as {{REP}},
with exactly these substitutions and nothing else changed:

1. Output roots
   - EVOSEARCH_DIR = outputs/claude_disagreement_r{{REP}}
   - EVALDIR       = outputs/aspire_disagreement_eval_r{{REP}}
   (also in the Stage 2 command: --fix-code outputs/claude_disagreement_r{{REP}}/.../evosearch_best_code.py
    --output-dir outputs/aspire_disagreement_eval_r{{REP}})
2. Parent selection: in every select_parents.py command use --rule disagreement instead of
   --rule top3 (selection.json then holds the disagreement parents). Everything else about parents is
   unchanged: only the script chooses them, children use only those parents, verify before each eval.
   parents.json uses "selection": "disagreement". Still exactly 8 candidates per round, same seeds,
   same stop rules, same evosearch_eval.py flags.
3. The subagent brief must include the rule description below verbatim.

Parent selection rule (disagreement)
- TODO: implement select_disagreement() in scripts/tc1/select_parents.py (it gets every candidate's
  per-seed 0/1 pass vector on seeds 51-65 and must return exactly 3 parents, deterministically), then
  replace this TODO with a one-paragraph description of the rule for the subagent brief.
- Everything that is not parent selection (candidate generation prompt, K, diagnosis, stop rules)
  stays identical to the evosearch arm.
