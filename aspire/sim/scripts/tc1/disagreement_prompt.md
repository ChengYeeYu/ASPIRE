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
2. Parent selection: replace "top-3 candidates of the current round by pass_rate" (runbook Step 6,
   item 3) with the rule below. Still exactly 8 candidates per round, same seeds, same stop rules,
   same evosearch_eval.py flags. parents.json uses "selection": "disagreement".
3. The subagent brief must include the rule below verbatim.

Parent selection rule (disagreement)
- TODO: define the rule. Fill in:
  - Signal: what "disagreement" is measured on (e.g. per-seed pass/fail vectors of the round's
    candidates from iter_NN/candidate_*/eval/, trace features, ...), and the exact computation.
  - Selection: how the parents for the next 8 candidates are chosen from it (how many parents,
    tie-breaks, whether pass_rate still gates them).
  - Script: path of any helper that computes it (e.g. scripts/tc1/disagreement_select.py), its
    command line, and the file it writes (e.g. iter_NN/selection.json) that parents.json must match.
- Everything that is not parent selection (candidate generation prompt, K, diagnosis, stop rules)
  stays identical to the evosearch arm.
