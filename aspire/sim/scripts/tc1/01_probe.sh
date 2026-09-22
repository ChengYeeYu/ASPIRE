#!/bin/bash
### TC1: probe the compute node (CPU only, no GPU) ###
#SBATCH --partition=UGGPU-TC1
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --mem=4G
#SBATCH --time=10
#SBATCH --job-name=aspire-probe
#SBATCH --output=logs/output_%x_%j.out
#SBATCH --error=logs/error_%x_%j.err

echo "== node: $(hostname)   date: $(date)"
echo "== home quota"; df -h "$HOME"
echo "== outbound internet (want HTTP/2 200 or 301/302; 000 = blocked)"
for u in https://download.pytorch.org https://huggingface.co https://github.com https://astral.sh https://api.anthropic.com https://pypi.org; do
  printf '%-32s %s\n' "$u" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$u")"
done
echo "== libEGL (needed for MUJOCO_GL=egl)"
ls -l /usr/lib64/libEGL* /usr/lib/x86_64-linux-gnu/libEGL* /usr/lib64/libOSMesa* 2>&1
echo "== modules"; module avail 2>&1 | grep -E "cuda|gcc|anaconda|miniconda"
echo "== toolchain"; gcc --version | head -1; cmake --version 2>&1 | head -1; git --version; tmux -V 2>&1
echo "== cpu/mem"; nproc; free -h | head -2
