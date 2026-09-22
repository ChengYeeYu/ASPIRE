#!/bin/bash
### TC1: working session = perception servers + Jupyter-Lab on 1 GPU (6 h max) ###
#SBATCH --partition=UGGPU-TC1
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --gres=gpu:1
#SBATCH --ntasks-per-node=16
#SBATCH --mem=60G
#SBATCH --time=360
#SBATCH --job-name=aspire-session
#SBATCH --output=logs/output_%x_%j.out
#SBATCH --error=logs/error_%x_%j.err

set -uxo pipefail
module load cuda/12.6 anaconda

cd "$HOME/ASPIRE/aspire/sim"
export ASPIRE_ROOT="$PWD"
export PYTHON_ROOT="$(cd ../.. && pwd)"
export HF_HOME="$HOME/.cache/huggingface"
export UV_CACHE_DIR="/tmp/$USER/uv" UV_LINK_MODE=copy   # NFS home has no file locking
export MUJOCO_GL=egl
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export PATH="$HOME/.local/bin:$PATH"       # uv + claude live here

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

# Jupyter from the shared env; token URL appears in logs/error_aspire-session_<jobid>.err
JPORT="${JPORT:-8891}"
source activate /tc1apps/2_conda_env/Jupyter
echo "== node ip $(hostname -i)  port $JPORT  -> tunnel: ssh -L $JPORT:$(hostname -i):$JPORT yu0001ee@10.96.189.11"
jupyter-lab --ip="$(hostname -i)" --port="$JPORT" --no-browser --notebook-dir="$HOME/ASPIRE/aspire/sim"
