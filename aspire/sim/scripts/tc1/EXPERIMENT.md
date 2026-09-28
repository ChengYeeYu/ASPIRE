# Experiment: disagreement selection vs evolutionary search (one task, TC1)

Task: `libero_goal_swap / put_the_bowl_on_the_stove`. One fix loop gives the shared starting point;
then evosearch and disagreement-selection runs, 1-3 repetitions each, all from that same start.
Files used: `fixloop_prompt.md`, `evosearch_prompt.md`, `disagreement_prompt.md`, `skills_snapshot.sh`.

All commands run on TC1 unless marked "laptop", from `~/ASPIRE/aspire/sim` (not `~/ASPIRE`).
Everything except `sbatch`/`squeue`/`scancel`/`git` runs in the Jupyter terminal (compute node) with the Phase 1 env block.

## Phase 0: get the files onto TC1 (once)
```bash
# laptop
cd ~/aspire_vla/ASPIRE && git push origin ChengYeeYu

# TC1 head node
ssh yu0001ee@10.96.189.11
cd ~/ASPIRE && git pull        # if it complains about fixloop_prompt.md: rm aspire/sim/scripts/tc1/fixloop_prompt.md, pull again
```

## Phase 1: start a session (every run)
```bash
# TC1 head node
module load slurm && cd ~/ASPIRE/aspire/sim
sbatch scripts/tc1/04_session.sh
squeue -u $USER                                          # wait for R; note <jobid>
grep -m1 'node ip' logs/error_aspire-session_<jobid>.err
grep -m1 -o 'http://[0-9.]*:8891/lab?token=[a-z0-9]*' logs/error_aspire-session_<jobid>.err
```
```bash
# laptop, new terminal, leave open
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
- Closing the browser tab / tunnel is fine. File > Shut Down or `scancel` kills the job.
- Job lasts 6 h: near the end, let Claude finish its current step, `/exit`, `scancel <jobid>`.

## Phase 2: fix loop (the shared starting point, run once)
```bash
# first run AND every resume after a job ended (new session, Phase 1 first)
claude "$(cat scripts/tc1/fixloop_prompt.md)"
```
```bash
# done when both succeed
cd ~/ASPIRE/aspire/sim
T=outputs/libero_fix_loop/libero_goal_swap/put_the_bowl_on_the_stove
.venv/bin/python3 scripts/libero/record_skill_promotion.py verify --suite libero_goal_swap --task put_the_bowl_on_the_stove
cat $T/validation_result.json                            # pass_rate = BASELINE_RATE (must be < 0.8)
```
```bash
# freeze the starting point (once) -- Jupyter terminal (compute node), not the head node
cd ~/ASPIRE/aspire/sim
T=outputs/libero_fix_loop/libero_goal_swap/put_the_bowl_on_the_stove
bash scripts/tc1/skills_snapshot.sh save after_fixloop
chmod a-w $T/fix_code.py $T/validation_result.json
mkdir -p ~/archive
tar czf ~/archive/fixloop_$(date +%Y%m%d).tgz outputs/libero_fix_loop outputs/libero_fix_loop_eval \
  outputs/libero_fix_loop_debug outputs/working_codes outputs/skill_snapshots/after_fixloop logs   # _debug = Stage 1 dev-seed replays
(cd ~/.claude/projects && tar czf ~/archive/fixloop_claude_$(date +%Y%m%d).tgz ./*ASPIRE-aspire-sim)   # ./ because the dir name starts with '-'
git -C ~/ASPIRE rev-parse HEAD > ~/archive/fixloop_commit.txt
```
Then `/exit` Claude and `scancel <jobid>` on the head node. Never rerun the fix loop on this task.

## Phase 3: one comparison run (repeat per arm and repetition)
Set these two values, then run the three blocks in order:
```bash
ARM=evosearch        # or: disagreement
REP=1                # 1, 2, 3
```
```bash
# (a) before: reset the starting point, check nothing carried over from earlier runs
cd ~/ASPIRE/aspire/sim
bash scripts/tc1/skills_snapshot.sh restore after_fixloop
ls ~/.claude/projects/*ASPIRE-aspire-sim/memory/ 2>/dev/null        # must be empty/absent; else move it aside
git -C ~/ASPIRE status --short -- '*.md'                            # no changed CLAUDE.md/runbooks (git checkout -- <file>)
claude "$(sed "s/{{REP}}/$REP/g" scripts/tc1/${ARM}_prompt.md)"
```
In Claude: check the preflight (BASELINE_RATE matches Phase 2, roots end in `_r$REP`), say "go", approve commands.
Same `/model` in every run. Fresh `claude` per run, never `--continue` across runs.

Job ended mid-run: new session, same `ARM`/`REP`, run block (a) WITHOUT the `restore` line; it resumes itself.
Never start a different arm/repetition while one is half-finished.
```bash
# (b) after the final report (Stage 2 manifest "complete")
bash scripts/tc1/skills_snapshot.sh check after_fixloop             # must print OK
grep -h '"status"' outputs/aspire_${ARM}_eval_r${REP}/libero_goal_swap/put_the_bowl_on_the_stove/runs/*/manifest.json 2>/dev/null   # "complete" (absent = fallback to fix_code)
```
```bash
# (c) archive (TC1 home has no backup) -- Jupyter terminal, before scancel
cd ~/ASPIRE/aspire/sim
tar czf ~/archive/${ARM}_r${REP}_$(date +%Y%m%d).tgz \
  outputs/claude_${ARM}_r${REP} $(ls -d outputs/aspire_${ARM}_eval_r${REP} 2>/dev/null) logs
(cd ~/.claude/projects && tar czf ~/archive/${ARM}_r${REP}_claude_$(date +%Y%m%d).tgz ./*ASPIRE-aspire-sim)
git -C ~/ASPIRE rev-parse HEAD > ~/archive/${ARM}_r${REP}_commit.txt
```
Then `/exit` Claude and `scancel <jobid>` on the head node.

## Run order
| # | ARM | REP | Needs |
|---|---|---|---|
| 1 | evosearch | 1 | Phase 2 done |
| 2 | disagreement | 1 | TODO in `disagreement_prompt.md` replaced with the rule |
| 3 | disagreement | 2 | |
| 4 | evosearch | 2 | |
| 5-6 | evosearch -> disagreement | 3 | optional |

Arm order alternates per repetition so time/quota drift doesn't favour one arm.

## Phase 4: compare (any time, from `~/ASPIRE/aspire/sim`)
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
Also compare `iter_NN/parents.json` (which parents each round used, and their rates).
With 50 held-out seeds, a single rate is about +-7 pp and an arm difference about +-10 pp, so
differences under ~15-20 pp from one repetition are not conclusive.
```bash
# laptop: pull archives
mkdir -p ~/aspire_vla/archive && scp 'yu0001ee@10.96.189.11:~/archive/*' ~/aspire_vla/archive/
```
