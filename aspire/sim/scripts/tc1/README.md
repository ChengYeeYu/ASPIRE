# TC1 (NTU CCDS GPU cluster) job scripts

QoS `normal`: 1 GPU, 20 CPUs, 64 GB, 2 jobs, **6 h wall**. No compute on the head node.
All scripts assume the repo is cloned at `~/ASPIRE` and are submitted from `~/ASPIRE/aspire/sim`.

| Script | GPU | Purpose |
|---|---|---|
| `01_probe.sh` | no | Check internet, libEGL, modules on a compute node. Run first. |
| `02_install.sh` | no | uv + `.venv` + `.venv-libero` + LIBERO config. ~2-3 h. |
| `03_smoke.sh` | yes | `pytest tests/test_libero.py` under EGL. No credentials. |
| `04_session.sh` | yes | SAM3 + GraspNet + PyRoKi on GPU 0 + Jupyter-Lab. Tunnel in and work. |

```bash
cd ~/ASPIRE/aspire/sim && mkdir -p logs
sbatch scripts/tc1/01_probe.sh
```

Between 02 and 03, on the head node: `.venv-libero/bin/hf auth login` (needs gated `facebook/sam3` access).

Session workflow: `sbatch scripts/tc1/04_session.sh` → `squeue -u $USER` → `tail -f logs/error_aspire-session_<id>.err`
for the tunnel line and Jupyter token → from laptop `ssh -L 8891:<node-ip>:8891 yu0001ee@10.96.189.11` →
open `http://127.0.0.1:8891/lab?token=...` → Terminal. `scancel <id>` when done.
