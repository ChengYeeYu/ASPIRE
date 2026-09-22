#!/bin/bash
### TC1: install ASPIRE base + LIBERO envs (CPU only, no GPU) ###
#SBATCH --partition=UGGPU-TC1
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=8
#SBATCH --mem=32G
#SBATCH --time=240
#SBATCH --job-name=aspire-install
#SBATCH --output=logs/output_%x_%j.out
#SBATCH --error=logs/error_%x_%j.err

set -euxo pipefail
module load cuda/12.6 gcc/13.3.0

cd "$HOME/ASPIRE/aspire/sim"
export ASPIRE_ROOT="$PWD"
export PYTHON_ROOT="$(cd ../.. && pwd)"
# keep every cache on the 300 GB home, never /tmp
export UV_CACHE_DIR="$HOME/.cache/uv"
export HF_HOME="$HOME/.cache/huggingface"
export TMPDIR="$HOME/tmp"; mkdir -p "$TMPDIR"

# uv (user-space, no sudo)
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
source "$HOME/.local/bin/env"
uv --version

bash scripts/common/apply_contact_graspnet_patch.sh

# base tools env (py3.10)
uv python install 3.10 3.12
[ -d .venv ] || uv venv .venv --python 3.10
uv sync --locked

# LIBERO env (py3.12) -- --active must run in the same shell as the activate
[ -d .venv-libero ] || uv venv .venv-libero --python 3.12
source .venv-libero/bin/activate
uv sync --locked --active --extra libero --extra contactgraspnet --extra dev
deactivate

# LIBERO path config (required by upstream LIBERO, else it prompts and dies on EOF)
mkdir -p "$HOME/.libero"
cat > "$HOME/.libero/config.yaml" <<YAML
benchmark_root: ${ASPIRE_ROOT}/cap/third_party/LIBERO-PRO/libero/libero
bddl_files: ${ASPIRE_ROOT}/cap/third_party/LIBERO-PRO/libero/libero/bddl_files
init_states: ${ASPIRE_ROOT}/cap/third_party/LIBERO-PRO/libero/libero/init_files
datasets: ${ASPIRE_ROOT}/cap/third_party/LIBERO-PRO/libero/datasets
assets: ${ASPIRE_ROOT}/cap/third_party/LIBERO-PRO/libero/libero/assets
YAML

echo "== verify"
.venv-libero/bin/python3 -c "import libero, robosuite, sam3, contact_graspnet_pytorch; print('libero env ok')"
.venv/bin/python3 -c "import importlib.util; print('libero in base env (want None):', importlib.util.find_spec('libero'))"
.venv-libero/bin/python3 -c "import torch; print('torch', torch.__version__, 'cuda build', torch.version.cuda)"
du -sh .venv .venv-libero "$UV_CACHE_DIR"
echo "== INSTALL DONE. Next (on head node): .venv-libero/bin/hf auth login"
