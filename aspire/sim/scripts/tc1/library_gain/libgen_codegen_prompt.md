Code generation for the library-gain measurement (scripts/tc1/library_gain/LIBGEN.md). You are the coordinator.
You only dispatch subagents and check their output. You write no robot code yourself, run no
simulator, and never edit the skill library.

Inputs
- ROOT  = {{ROOT}}
- PHASE = {{PHASE}}
- ROOT/manifest.json (suite, K, seeds) and ROOT/PHASE/phase.json (tasks of this phase) already exist.
- Every slot to fill is ROOT/PHASE/<id>/candidate_<X>/ for each task id in phase.json "tasks" and
  X in the first K letters (A, B, C, ...). A slot is done when its code.py exists and is non-empty.
- A task id is <suite>/<task>: SUITE is the part before the first "/", TASK the rest.
  Its scene probe is ROOT/probe/<id>.txt.

Procedure
1. Run  .venv/bin/python3 scripts/tc1/library_gain/libgen.py status --root ROOT --phase PHASE
   It must print "library ... OK". If it says CHANGED, stop and tell me.
2. For every slot WITHOUT code.py, dispatch ONE subagent with the template below (fill the 5
   placeholders; nothing else in it may change between slots, tasks or phases). Dispatch with
   NO model override. At most 4 subagents running at a time; keep dispatching until all slots
   are filled. Order: task by task, candidates A..K.
3. A slot whose subagent returned without a non-empty code.py: re-dispatch it ONCE with the same
   template. If it fails again, leave it empty, go on, and list it in your final report.
4. Do not open, compare or "fix" any code.py. Never tell a subagent what other candidates did.
5. End with step 1's status output and: slots filled, slots re-dispatched, slots still empty,
   the model you ran on. Then stop -- evaluation is run outside this session.

Rules for this session
- Resuming: just repeat from step 1; filled slots are skipped.
- Do not read scripts/tc1/**/*.md other than this file, docs/logs/, or anything under outputs/ except
  ROOT/manifest.json, ROOT/PHASE/phase.json and the status output. Do not save memories.
- CLAUDE.md's "Self-Evolve"/"Log Everything" rules are suspended: no skill edits, no docs/logs.
- Never push to any remote.

----- subagent template (fill SUITE, TASK, PROBE, OUT, X) -----
You write ONE robot program, zero-shot, for a LIBERO task. No simulator runs, no debugging.

SUITE: <SUITE>
TASK:  <TASK>
Scene probe (read it): <PROBE>
Write your program to: <OUT>/code.py      (candidate <X>)

Read, in this order, and nothing else:
1. CLAUDE.md -- only the FORBIDDEN APIs and ALLOWED APIs sections.
2. .claude/libero/api-reference.md
3. Every file in .claude/libero/skills/ (the skill library -- reuse its helpers and patterns).
   The library may be empty; then write the program from the API alone.
4. The scene probe file above: task language, SAM3 detections, 3D centres/extents on ONE seed.
5. If you need exact signatures: cap/integrations/franka/libero_reduced_skill_library.py and
   cap/integrations/franka/libero_reduced.py.
(paths relative to aspire/sim, which is the current directory)

Forbidden: running the simulator or any eval/replay script; reading anything under outputs/ other
than the probe file and your own output dir; reading scripts/tc1/, docs/, other tasks' or other
candidates' code; editing any file except <OUT>/code.py.

The program
- Plain Python executed once per episode with the API functions already in scope (as in the skill
  library examples); no __main__ guard needed. It must solve the task from perception alone on any
  seed: object positions change per seed, so localise at run time; the probe's numbers are only
  for scale.
- Read the instruction from env.handle.task_language.
- Only ALLOWED APIs, numpy, scipy, math. Episode budget is 4000 env steps, keep motions purposeful.
- Check it compiles:  python3 -m py_compile <OUT>/code.py

Return in at most 3 lines: the path written, the approach in one line, which skill-library
helpers/patterns you used.
