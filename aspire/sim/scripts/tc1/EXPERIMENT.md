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
claude "$(sed "s/{{REP}}/$REP/g" scripts/tc1/${ARM}_prompt.md)"
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
for d in $R/iter_*/; do [ -f $d/iter_summary.json ] || mv $d ${d%/}_partial_$(date +%H%M); done   # set aside the unfinished round
bash scripts/tc1/skills_snapshot.sh check after_fixloop
ls $R; ls outputs/claude_${ARM}_r${REP}/libero_goal_swap/put_the_bowl_on_the_stove/
claude "$(sed "s/{{REP}}/$REP/g" scripts/tc1/${ARM}_prompt.md)

RESUMING NOW (unattended, I'm away -- never stop to ask; make the protocol-compliant choice and note it):
- RUN_DIR $R: rounds with iter_summary.json are complete. Any iter_*_partial_* is a discarded interrupted attempt -- ignore it.
- Skip preflight approval. If evosearch_best_code.py does not exist: dispatch ONE subagent continuing this RUN_DIR
  from the next round (parents = the last complete round's selection.json; if it is missing, run
  select_parents.py select for that round first; verify before each eval).
  If it exists: skip Stage 1 and run/resume Stage 2 only (--resume skips finished seeds).
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
tar czf ~/archive/${ARM}_r${REP}_$(date +%Y%m%d).tgz \
  outputs/claude_${ARM}_r${REP} $(ls -d outputs/aspire_${ARM}_eval_r${REP} 2>/dev/null) logs
(cd ~/.claude/projects && tar czf ~/archive/${ARM}_r${REP}_claude_$(date +%Y%m%d).tgz ./*ASPIRE-aspire-sim)
git -C ~/ASPIRE rev-parse HEAD > ~/archive/${ARM}_r${REP}_commit.txt
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
| 3 | disagreement | 1 | TODO in `disagreement_prompt.md` replaced with the rule |
| 4 | disagreement | 2 | |
| 5-6 | disagreement -> evosearch | 3 | optional |

Evosearch reached 98% held-out here, so final rates can't separate the arms on this task: compare
rounds-to->=80%, per-round best/mean, and parent rates (`parents.json`) across repetitions -- or move
to a harder task (new fix loop) to compare final rates.

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
