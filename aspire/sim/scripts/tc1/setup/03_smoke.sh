#!/bin/bash
### TC1: credential-free LIBERO smoke test (1 GPU) ###
#SBATCH --partition=UGGPU-TC1
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --gres=gpu:1
#SBATCH --ntasks-per-node=4
#SBATCH --mem=16G
#SBATCH --time=30
#SBATCH --job-name=aspire-smoke
#SBATCH --output=logs/output_%x_%j.out
#SBATCH --error=logs/error_%x_%j.err

set -euxo pipefail
module load cuda/12.6

cd "$HOME/ASPIRE/aspire/sim"
export ASPIRE_ROOT="$PWD"
export PYTHON_ROOT="$(cd ../.. && pwd)"
export HF_HOME="$HOME/.cache/huggingface"
export MUJOCO_GL=egl
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1

nvidia-smi
.venv-libero/bin/python3 -c "import torch; print('cuda available:', torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# loads a LIBERO-10 task, resets from a benchmark init state, takes 10 zero-action steps
ASPIRE_INTEGRATION_REAL=1 .venv-libero/bin/python -m pytest tests/test_libero.py -q
echo "== SMOKE TEST PASSED"
