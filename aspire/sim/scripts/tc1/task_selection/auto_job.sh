#!/bin/bash
### TC1: unattended task-selection arm = perception servers + auto.py on 1 GPU (6 h max) ###
# Submit once from the head node (in ~/ASPIRE/aspire/sim):  ARM=disagreement sbatch scripts/tc1/task_selection/auto_job.sh
# At start it submits its own successor (afterany = runs when this job ends, also on TIMEOUT), so
# the chain survives the 6 h limit. The successor is cancelled when auto.py ends with done/error.
# Stop: touch outputs/task_selection/$ARM/auto/STOP (driver stops at the next step boundary),
# or scancel both jobs. Chain length is capped by AUTO_MAX_JOBS (default 10).
#SBATCH --partition=UGGPU-TC1
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --gres=gpu:1
#SBATCH --ntasks-per-node=16
#SBATCH --mem=60G
#SBATCH --time=360
#SBATCH --job-name=aspire-auto
#SBATCH --output=logs/output_%x_%j.out
#SBATCH --error=logs/error_%x_%j.err

set -uxo pipefail
DEADLINE=$(( $(date +%s) + 355 * 60 ))
ARM="${ARM:-disagreement}"
module load cuda/12.6 slurm

cd "$HOME/ASPIRE/aspire/sim"
export ASPIRE_ROOT="$PWD"
export PYTHON_ROOT="$(cd ../.. && pwd)"
export HF_HOME="$HOME/.cache/huggingface"
export UV_CACHE_DIR="/tmp/$USER/uv" UV_LINK_MODE=copy   # NFS home has no file locking
export MUJOCO_GL=egl
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export PATH="$HOME/.local/bin:$PATH"       # uv + claude live here

A="outputs/task_selection/$ARM/auto"
mkdir -p "$A"
if [[ -f "$A/STOP" ]]; then echo "STOP file $A/STOP present -- not starting"; exit 0; fi
if [[ -f "$A/FAILED" ]]; then echo "previous run failed: $(cat "$A/FAILED") -- fix it, rm $A/FAILED, resubmit"; exit 0; fi

N=$(( $(cat "$A/job_count" 2>/dev/null || echo 0) + 1 )); echo "$N" > "$A/job_count"
NEXT=""
if (( N < ${AUTO_MAX_JOBS:-10} )); then
  NEXT=$(ARM="$ARM" sbatch --parsable --dependency="afterany:$SLURM_JOB_ID" scripts/tc1/task_selection/auto_job.sh) || NEXT=""
fi
echo "$(date '+%F %T') job $SLURM_JOB_ID (#$N) on $(hostname), successor ${NEXT:-NONE}" >> "$A/jobs.log"
[[ -z "$NEXT" ]] && echo "WARNING: no successor job -- resubmit by hand from the head node when this one ends"

# everything shares the single V100 (paper used separate GPUs)
export ASPIRE_PERCEPTION_PYTHON=.venv-libero/bin/python3
export SAM3_GPU=0 GRASPNET_GPU=0 SIM_GPU=0
bash scripts/common/start_perception_servers.sh --no-molmo --gpu-sam3 0 --gpu-graspnet 0

echo "== waiting for perception servers (404 on /health = up, 000 = down)"
for i in $(seq 1 60); do
  s=""; for p in 8114 8115 8116; do s="$s $p:$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:$p/health)"; done
  echo "$s"; [[ "$s" != *":000"* ]] && break; sleep 10
done
nvidia-smi --query-gpu=memory.used,memory.total --format=csv

.venv/bin/python3 scripts/tc1/task_selection/auto.py --arm "$ARM" --deadline "$DEADLINE" \
  --model "${AUTO_MODEL:-claude-sonnet-5}" --claude-flags "${AUTO_CLAUDE_FLAGS:---permission-mode auto}"
rc=$?
echo "$(date '+%F %T') job $SLURM_JOB_ID: auto.py rc=$rc" >> "$A/jobs.log"
# 10 = out of time: the successor continues. 0 = arm done, else error: no successor.
if [[ $rc -ne 10 && -n "$NEXT" ]]; then scancel "$NEXT"; fi
exit 0
