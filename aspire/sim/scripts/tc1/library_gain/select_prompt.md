Choose ONE task to debug next, for the library-gain measurement (arm {{ARM}}). A fix loop will be run
on the task you choose and its lessons promoted to the shared skill library; the goal is the task
whose debugging will most improve the library for the OTHER tasks.

Read ONLY this file: {{ROOT}}/{{PHASE}}/summary.json
It has, per task, results of K programs written zero-shot from the current library, each run on the
same seeds:
- mean_rate: mean success of the K programs (main number)
- best_rate: the best single program
- any_pass_rate: share of seeds solved by at least one program
- programs_with_any_pass: how many of the K programs passed at least one seed
- seed_disagreement: share of seeds where some programs pass and some fail
- rates: each program's success rate
Do not open any other file, code, log or output, and do not run anything except writing the result.

Selection rule
- If most tasks have LOW success rates: choose a task with a HIGH success rate (among them, the
  one most worth debugging).
- If all tasks have MODERATE or HIGH success rates: choose the task with the LOWEST success rate.
- Decide yourself what counts as low / moderate / high and as "most" for these numbers, and say so.
- If the numbers fit neither case, say that the case is "mixed", choose the task you judge most
  worth debugging, and explain why.
Use the other fields (best_rate, any_pass_rate, disagreement) to break ties or near-ties, and say
when you did.

Write {{ROOT}}/select_{{ARM}}.json and nothing else:
{
  "arm": "{{ARM}}",
  "phase": "{{PHASE}}",
  "case": "most_low" | "all_moderate_high" | "mixed",
  "thresholds": "<your low / moderate / high cut-offs and what 'most' meant>",
  "chosen_task": "<task name exactly as in summary.json>",
  "runner_up": "<task name>",
  "reasoning": "<3-6 sentences, citing the numbers>"
}
Then print the file and stop.
