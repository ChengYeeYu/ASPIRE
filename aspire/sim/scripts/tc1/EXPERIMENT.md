# Experiment: disagreement selection vs evolutionary search (one task, TC1)

Task: `libero_goal_swap / put_the_bowl_on_the_stove`. One fix loop gives the shared starting point;
then evosearch and disagreement-selection runs, 1-3 repetitions each, all from that same start.
Files used: `fixloop_prompt.md`, `evosearch_prompt.md`, `disagreement_prompt.md`, `skills_snapshot.sh`,
`run_cost.py` (time + tokens per run), `select_parents.py` (parent selection as code: `--rule top3` for evosearch, `--rule disagreement` for the
new arm; the agent only writes candidates). From r2 on, both arms use it; r1's parents were agent-chosen.

All commands run on TC1 unless marked "laptop", from `~/ASPIRE/aspire/sim` (not `~/ASPIRE`).
Everything except `sbatch`/`squeue`/`scancel`/`git`/quick `ls`/`grep` runs in the Jupyter terminal
(compute node) with the Phase 1 env block. `scp` always runs on the laptop.

## Results so far
| Run | Model | Search (dev 51-65, best per round) | Held-out 1-50 | Time / tokens (run_cost.py) | Notes |
|---|---|---|---|---|---|
| fix loop | Sonnet 5 (1 Opus 5.5 call) | - | 2/50 (4%) | agent 2h15m; 194 calls, 40k output, 30.5M cache-read | shared start; snapshot `after_fixloop` |
| evosearch r1 | Sonnet 5 | 13% -> 73% -> 93% (solved in 3 rounds) | 49/50 (98%), failed seed 49 | 5h40m (rounds 1h42/1h52/1h12, Stage 2 47m); 244 calls, 122k output, 29.9M cache-read | iter_01 eval killed at 98/120 (23:23), re-run in full, evals detached from then on; job change at 00:42. **Parents chosen by the agent** (before select_parents.py): strict top-3 would be B,E,C then G,C,A; agent used B,E,H then G,C,H + A |
| evosearch r2 | Sonnet 5 (`--model`) | 20% -> 47% -> 47% -> 53% -> 67% (not solved, 5-round cap; best iter_04/F) | 19/50 (38%) | 7h38m (rounds 1h15/1h20/1h13/1h12/1h50, Stage 2 47m); 222 calls, 73k output, 43.5M cache-read | script top-3 parents (first run with select_parents.py). job 66244 timed out at iter_04 66/120; re-run gave identical results on all 66 overlapping trials. Held-out failures (31): 17 arm stopped ~14 cm short of release, 14 reached release height but failed (cause TBD), per trace.json; r1: 1 (see FINDINGS.md F2). Attempt 1 (09:44-10:26, Sonnet 5.5 by mistake) discarded to ~/archive/discarded_evosearch_r2_sonnet55_20260929 |
| disagreement r1 | Sonnet 5 (`--model`) | 13% -> 33% -> 27% -> 33% -> 47% (not solved, 5-round cap; best iter_04/H) | 23/50 (46%) | 8h47m (rounds 1h13/1h18/1h21/2h24/1h21, Stage 2 1h07); 132 calls, 31k output, 21.8M cache-read -- **tokens look undercounted** (1 session, 0 calls in iter_04; 8 new ~200-line candidates per round can't fit in ~2k output) | parents = same set as top3 in all 5 rounds (only order differs; see FINDINGS.md F7). iter_03 eval crashed at 76/120 (23:58), re-run. Held-out failures (27): 22 stopped short, 5 at release height. Repeats cut 3->2 from iter_03 on |

## Phase 0: get the files onto TC1 (after every local commit)
```bash
# laptop
cd ~/aspire_vla/ASPIRE && git push origin ChengYeeYu

# TC1 head node
cd ~/ASPIRE && git pull
```

## Phase 1: start a session (every run / every resume)
```bash
# TC1 head node
module load slurm && cd ~/ASPIRE/aspire/sim
squeue -u $USER                                          # no old session still running (else scancel it)
sbatch scripts/tc1/04_session.sh
squeue -u $USER                                          # wait for R; note <jobid>
grep -m1 'node ip' logs/error_aspire-session_<jobid>.err
grep -m1 -o 'http://[0-9.]*:8891/lab?token=[a-z0-9]*' logs/error_aspire-session_<jobid>.err
```
```bash
# laptop, new terminal, leave open (it logs you into the head node -- don't type in it)
ssh -L 8891:<node-ip>:8891 yu0001ee@10.96.189.11
# browser: http://127.0.0.1:8891/lab?token=<token>  ->  File > New > Terminal
```
```bash
# Jupyter terminal: env + checks (every new terminal)
hostname                                                 # TC1Nxx, not CCDS-TC1
cd ~/ASPIRE/aspire/sim
export PATH="$HOME/.local/bin:$PATH"
export ASPIRE_ROOT=$PWD PYTHON_ROOT=$(cd ../.. && pwd) MUJOCO_GL=egl TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export UV_CACHE_DIR=/tmp/$USER/uv UV_LINK_MODE=copy
for p in 8114 8115 8116; do echo -n "$p: "; curl -s -o /dev/null -w '%{http_code}\n' --max-time 3 http://127.0.0.1:$p/health; done   # all 404
```
- Closing the browser tab / tunnel / laptop is fine. File > Shut Down or `scancel` kills the job.
- Jobs last 6 h. To use a night fully, start a fresh job right before sleeping (see Phase 3, resume).
- Don't open files under `.claude/libero/skills/` in the Jupyter editor (it creates `.ipynb_checkpoints/`);
  use `cat`/`less`.

## Phase 2: fix loop (the shared starting point) -- DONE 28 Sep 2026
```bash
claude "$(cat scripts/tc1/fixloop_prompt.md)"          # first run AND every resume
```
```bash
# done when both succeed
T=outputs/libero_fix_loop/libero_goal_swap/put_the_bowl_on_the_stove
.venv/bin/python3 scripts/libero/record_skill_promotion.py verify --suite libero_goal_swap --task put_the_bowl_on_the_stove
cat $T/validation_result.json                            # pass_rate = BASELINE_RATE (must be < 0.8)
```
```bash
# freeze the starting point (once, Jupyter terminal)
bash scripts/tc1/skills_snapshot.sh save after_fixloop
chmod a-w $T/fix_code.py $T/validation_result.json
mkdir -p ~/archive
tar czf ~/archive/fixloop_$(date +%Y%m%d).tgz outputs/libero_fix_loop outputs/libero_fix_loop_eval \
  outputs/libero_fix_loop_debug outputs/working_codes outputs/skill_snapshots/after_fixloop logs   # _debug = Stage 1 dev-seed replays
(cd ~/.claude/projects && tar czf ~/archive/fixloop_claude_$(date +%Y%m%d).tgz ./*ASPIRE-aspire-sim)   # ./ because the dir name starts with '-'
git -C ~/ASPIRE rev-parse HEAD > ~/archive/fixloop_commit.txt
```
Never rerun the fix loop on this task.

## Phase 3: one comparison run (repeat per arm and repetition)

### (a) start a run
```bash
# Jupyter terminal, after the Phase 1 env block
ARM=evosearch        # or: disagreement
REP=2                # next unused repetition
rm -rf outputs/skill_snapshots/after_fixloop/.ipynb_checkpoints .claude/libero/skills/.ipynb_checkpoints
bash scripts/tc1/skills_snapshot.sh restore after_fixloop
bash scripts/tc1/skills_snapshot.sh check after_fixloop             # OK
ls ~/.claude/projects/*ASPIRE-aspire-sim/memory/ 2>/dev/null        # empty/absent, else: mv it to ~/archive/<name>_memory
ls docs/logs/                                                       # only .gitkeep, else move the logs to ~/archive/
git -C ~/ASPIRE status --short -- '*.md'                            # only skills grasp.md/transport.md + docs/progress (expected)
ls -d outputs/claude_${ARM}_r${REP} 2>/dev/null                     # must NOT exist yet
grep -c setsid scripts/tc1/evosearch_prompt.md                      # >= 1 (latest prompt pulled)
claude --model claude-sonnet-5 "$(sed "s/{{REP}}/$REP/g" scripts/tc1/${ARM}_prompt.md)"
```
Check the preflight before saying "go":
- BASELINE_RATE 4% (2/50), START_CODE = fix-loop `fix_code.py`
- roots `outputs/claude_${ARM}_r${REP}` and `outputs/aspire_${ARM}_eval_r${REP}`
- model = **Sonnet 5** (same as r1; `/model` before "go" if not)
- evals detached (`setsid nohup`), ONE subagent, GPU 0, `--parallel-per-gpu 2`, skills check OK

Fresh `claude` per run; never `--continue` across runs. Never start another arm/rep while one is half-finished.

### (b) monitor (second Jupyter terminal; read-only)
```bash
R=$(ls -d outputs/claude_${ARM}_r${REP}/libero_goal_swap/put_the_bowl_on_the_stove/2*/ | tail -1)
date
for d in $R/iter_*/; do echo "$(basename $d): trials=$(grep -c 'reward=' $d/eval.log 2>/dev/null) summary=$([ -f $d/iter_summary.json ] && echo yes || echo no)"; done
grep -ho '"best_pass_rate": [0-9.]*' $R/iter_*/iter_summary.json
ps -ef | grep -E 'evosearch_eval|replay_trial|run_fix_loop_validation' | grep -v grep | wc -l   # >0 while an eval runs
```
- One round = 120 trials (the eval counter says "/400": cosmetic, it stops at 120), ~40-60 min.
- "Agent ... finished" lines while an eval runs are normal (the worker pauses between polls).
- **Eval dead** (counter frozen >10 min AND no eval process): tell Claude
  "iter_NN eval is dead at <n>/120 since <time>; keep the log as eval_crashed_<HHMM>.log, clear the
  round's partial outputs, re-run the round with identical flags (detached); one worker only."
- **Worker didn't wake** (`iter_summary.json` exists, no next `iter_*` after 15 min): tell Claude
  "iter_NN finished at <time> but the worker didn't continue; dispatch one fresh subagent continuing the same RUN_DIR."

### (c) resume after the job ended / before sleeping
Phase 1, then in the Jupyter terminal (NO `restore` line -- the library is already correct):
```bash
ARM=evosearch; REP=2
R=$(ls -d outputs/claude_${ARM}_r${REP}/libero_goal_swap/put_the_bowl_on_the_stove/2*/ | tail -1)
# unfinished round: keep it if its 8 candidates + parents.json verify (re-run its eval only), else set it aside
for d in $R/iter_*/; do [ -f $d/iter_summary.json ] && continue
  if [ $(ls $d/candidate_*/code.py 2>/dev/null | wc -l) -eq 8 ] && { [ $(basename $d) = iter_00 ] || .venv/bin/python3 scripts/tc1/select_parents.py verify --iter-dir $d; }; then
    mv $d/eval.log $d/eval_crashed_$(date +%H%M).log 2>/dev/null; rm -rf $d/candidate_*/eval $d/candidate_*/eval_results.json; echo "KEEP $d (re-evaluate)"
  else mv $d ${d%/}_partial_$(date +%H%M); echo "SET ASIDE $d"; fi; done
bash scripts/tc1/skills_snapshot.sh check after_fixloop
ls $R; ls outputs/claude_${ARM}_r${REP}/libero_goal_swap/put_the_bowl_on_the_stove/
claude --model claude-sonnet-5 "$(sed "s/{{REP}}/$REP/g" scripts/tc1/${ARM}_prompt.md)

RESUMING NOW (unattended, I'm away -- never stop to ask; make the protocol-compliant choice and note it):
- RUN_DIR $R: rounds with iter_summary.json are complete. Any iter_*_partial_* is a discarded interrupted attempt -- ignore it.
  A round WITHOUT iter_summary.json but with 8 candidate code.py files was kept on purpose: do not rewrite its
  candidates; just re-run its eval (identical flags, detached), then continue.
- Skip preflight approval. If evosearch_best_code.py does not exist: dispatch ONE subagent continuing this RUN_DIR
  from the next round (parents = the last complete round's selection.json; if it is missing, run
  select_parents.py select for that round first; verify before each eval).
  If it exists: skip Stage 1 and run/resume Stage 2 only (--resume skips finished seeds).
- When Stage 1 stops (>=80% or 5 rounds done), pick the final code with select_parents.py best (not by judgment).
- Launch every eval detached (setsid nohup ... &) and poll for iter_summary.json; Stage 2 detached the same way."
```
Wait until an `Agent(...)` line (or the Stage 2 launch) appears before walking away.

### (d) after the run (Stage 2 manifest "complete")
```bash
E=outputs/claude_${ARM}_r${REP}/libero_goal_swap/put_the_bowl_on_the_stove
H=outputs/aspire_${ARM}_eval_r${REP}/libero_goal_swap/put_the_bowl_on_the_stove
ls $H/runs/                                                         # exactly ONE run id (absent = fallback to fix_code)
grep -h -E '"passes"|"trials"|"status"' $H/runs/*/manifest.json     # "complete", passes/50
grep -h -A16 '"trial_seeds"' $E/2*/iter_*/iter_summary.json | grep -oE '\b[0-9]+\b' | sort -un | tr '\n' ' '; echo   # only 51..65
for d in $E/2*/iter_0[1-9]; do .venv/bin/python3 scripts/tc1/select_parents.py verify --iter-dir $d; done   # every round OK
bash scripts/tc1/skills_snapshot.sh check after_fixloop             # OK
ls docs/logs/ ~/.claude/projects/*ASPIRE-aspire-sim/memory/ 2>/dev/null   # nothing new
.venv/bin/python3 scripts/tc1/run_cost.py --json ~/archive/run_cost_$(date +%Y%m%d).json   # time + tokens, all runs so far
```
### (e) archive (Jupyter terminal, before scancel)
```bash
if [ -n "$ARM" ] && [ -n "$REP" ] && [ -d outputs/claude_${ARM}_r${REP} ]; then   # new terminal? set ARM/REP first
tar czf ~/archive/${ARM}_r${REP}_$(date +%Y%m%d).tgz \
  outputs/claude_${ARM}_r${REP} $(ls -d outputs/aspire_${ARM}_eval_r${REP} 2>/dev/null) logs
(cd ~/.claude/projects && tar czf ~/archive/${ARM}_r${REP}_claude_$(date +%Y%m%d).tgz ./*ASPIRE-aspire-sim)
git -C ~/ASPIRE rev-parse HEAD > ~/archive/${ARM}_r${REP}_commit.txt
else echo "ARM/REP unset or outputs/claude_${ARM}_r${REP} missing -- nothing archived"; fi
ls -lh ~/archive
```
Then `/exit` Claude, `scancel <jobid>` on the head node, and on the laptop:
```bash
scp 'yu0001ee@10.96.189.11:~/archive/*' ~/aspire_vla/archive/
```
Add a row to "Results so far" (model, per-round best, held-out, time/tokens from run_cost.py, incidents).
Claude Code deletes old transcripts after ~30 days by default, so the `*_claude_*.tgz` archives are the
lasting source for token numbers: `run_cost.py --claude-dir <unpacked dir> --outputs <unpacked outputs>`.

## Run order
| # | ARM | REP | Status / needs |
|---|---|---|---|
| 1 | evosearch | 1 | DONE (98%) |
| 2 | evosearch | 2 | next (moved ahead of disagreement r1: rule not written yet) |
| 3 | disagreement | 1 | DONE (46%); rule never changed the parent set (FINDINGS.md F7) |
| 4 | disagreement | 2 | |
| 5-6 | disagreement -> evosearch | 3 | optional |
| 7 | evosearch_agent | 1 | next: original ASPIRE, parents and final pick chosen by the agent (like r1); prompt `evosearch_agent_prompt.md` |

Evosearch reached 98% held-out here, so final rates can't separate the arms on this task: compare
rounds-to->=80%, per-round best/mean, and parent rates (`parents.json`) across repetitions -- or move
to a harder task (new fix loop) to compare final rates.

## evosearch_agent arm (original ASPIRE parent selection)
Same as evosearch except the agent picks parents itself (runbook Step 6 "top-3 survivors") and the final
code (Step 7a); `parents.json` is still written, with `"selection": "agent"`. It repeats r1's condition
with the later fixes (detached evals, pinned model). Run it with `ARM=evosearch_agent REP=1` in Phase 3,
with these differences:
- (c) resume: in the RESUMING text replace "parents = the last complete round's selection.json ... verify
  before each eval" with "the subagent picks parents from the last complete round's leaderboard (runbook
  Step 6), writes parents.json", and the final-pick line with "pick the final code as in runbook Step 7a;
  run select_parents.py best for the record only". The keep/set-aside loop's `verify` fails for this arm:
  keep an unfinished round if it has 8 candidates and a parents.json.
- (d) skip the `select_parents.py verify` loop; check every `iter_0[1-9]/parents.json` exists instead.
  `best.json` is the script's pick for reference; Stage 2 used `evosearch_best_code.py` (agent pick).

## Disagreement rule (`select_disagreement`, decided 29 Sep 2026)
- Parent 1: most passes. Parents 2-3: among candidates passing >= `MIN_PASS_PCT` = 20% of the round's
  seeds (3/15), the one with the largest minimum Hamming distance (per-seed pass/fail) to the parents
  already chosen; ties: more passes, then name. Too few eligible -> fill by most passes (= top3).
- Why the floor: without it a 0/15 candidate is "most different" from a strong one just by failing
  (on r1 iter_01 it would pick B 0/15). Budget is unchanged: 8 candidates x max 5 rounds per arm.
- Dry run on any finished run: `.venv/bin/python3 scripts/tc1/select_parents.py compare --run-dir $RUN_DIR`.
  On r1: iter_00 same as top3 (nobody but the best reaches 3/15); iter_01 G C F vs top3 G C A;
  iter_02 F E C vs top3 F B A.
- The prompt only describes what the rule does. No "learn from the complementary failures" motivation
  in one arm only: that would change the rule and the instructions at once. To test that
  guidance, add a third arm (disagreement + guidance) instead.
- Write-up: the floor (20%) and the tie-break were chosen after seeing r1's data; say so. Report
  programs-to->=80% as well as held-out, since the >=80% stop ends the faster arm earlier.

## Phase 4: compare (any time)
```bash
.venv/bin/python3 - <<'EOF'
import json, glob
S = "libero_goal_swap/put_the_bowl_on_the_stove"
print("== held-out (seeds 1-50)")
for m in sorted(glob.glob(f"outputs/libero_fix_loop_eval/{S}/runs/*/manifest.json") +
                glob.glob(f"outputs/aspire_*_eval_r*/{S}/runs/*/manifest.json")):
    d = json.load(open(m))
    print(f"  {m.split('/')[1]:<32} {d['passes']:>2}/{d['trials']}  {d['pass_rate']:.0%}  {d['status']}")
print("== search rounds (seeds 51-65)")
for s in sorted(glob.glob(f"outputs/claude_*_r*/{S}/*/iter_*/iter_summary.json")):
    r = sorted((c["pass_rate"] for c in json.load(open(s))["candidates"]), reverse=True)
    print(f"  {s.split('/')[1]:<26} {s.split('/')[-2]}  best={r[0]:.0%}  mean={sum(r)/len(r):.0%}  top3={[round(x*100) for x in r[:3]]}")
EOF
```
With 50 held-out seeds, a single rate is about +-7 pp and an arm difference about +-10 pp, so
differences under ~15-20 pp from one repetition are not conclusive. Dev-seed rates are noisier still:
GraspNet is stochastic, so the same code on the same seed can pass once and fail the next time.

## Inspecting results
Laptop (reading + videos), from the archives:
```bash
mkdir -p ~/aspire_vla/inspect && cd ~/aspire_vla/inspect
tar xzf ../archive/${ARM}_r${REP}_<date>.tgz                        # e.g. evosearch_r1_20260929.tgz
code ~/aspire_vla/inspect                                           # findings.md, evosearch_best_code.py, iter_*/
# videos: cd into .../runs/<id>/results/.../run/ and `explorer.exe .`, then open trial_NN_*/video_*.mp4
```
(`aws_anthropic_bedrock-claude-sonnet-4-6` in the trial path is only replay_trial's default label; no model is called.)
Compare code: VS Code Explorer, right-click fix-loop `fix_code.py` -> Select for Compare, right-click
`evosearch_best_code.py` -> Compare with Selected.

Run it yourself (TC1 GPU session only -- the laptop GPU is too small), always into `outputs/inspect`:
```bash
E=outputs/claude_evosearch_r1/libero_goal_swap/put_the_bowl_on_the_stove
CUDA_VISIBLE_DEVICES=0 .venv-libero/bin/python3 scripts/libero/replay_trial.py \
  --args.suite libero_goal_swap --args.task put_the_bowl_on_the_stove --args.trial 120 \
  --args.replay-code $E/evosearch_best_code.py \
  --args.config env_configs/libero/franka_libero_traced.yaml --args.output-dir outputs/inspect
# interactive: replace --args.replay-code ... --args.output-dir ... with  --args.interactive --args.no-record-video
.venv/bin/python3 scripts/common/analyze_trial.py --trial-dir <trial dir> --verbose
```
Seeds >=100 have never been seen by any run: a free extra generalization check.
