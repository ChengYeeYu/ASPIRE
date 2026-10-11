# TC1 (NTU CCDS GPU cluster) scripts and experiments

QoS `normal`: 1 GPU, 20 CPUs, 64 GB, 2 jobs, **6 h wall**. No compute on the head node.
All scripts assume the repo is cloned at `~/ASPIRE` and are run from `~/ASPIRE/aspire/sim`.

| Folder | What |
|---|---|
| [setup/](setup/) | SLURM job scripts (probe, install, smoke test, GPU + Jupyter session); `TC1_NOTES.md` (local only) |
| [common/](common/) | `skills_snapshot.sh`: save / restore / check / save-git the skill library (used by both experiments) |
| [parent_selection/](parent_selection/) | One task (`put_the_bowl_on_the_stove`): fix loop, then evosearch vs disagreement / agent-chosen / behaviour-tree parent selection. Runbook + results: `EXPERIMENT.md`, analysis: `FINDINGS.md` |
| [library_gain/](library_gain/) | One suite (`libero_goal_swap`, 10 tasks): how much a skill-library update raises zero-shot success on the other tasks. Runbook: `LIBGEN.md` |
| [task_selection/](task_selection/) | 9 tasks over goal/spatial/object swap, library built from empty: which task to fix next, disagreement vs top-to-bottom, 3 rounds. Runbook: `TASKSEL.md` (uses `library_gain/libgen.py` for codegen + eval) |

## Setup jobs

| Script | GPU | Purpose |
|---|---|---|
| `setup/01_probe.sh` | no | Check internet, libEGL, modules on a compute node. Run first. |
| `setup/02_install.sh` | no | uv + `.venv` + `.venv-libero` + LIBERO config. ~2-3 h. |
| `setup/03_smoke.sh` | yes | `pytest tests/test_libero.py` under EGL. No credentials. |
| `setup/04_session.sh` | yes | SAM3 + GraspNet + PyRoKi on GPU 0 + Jupyter-Lab. Tunnel in and work. |

```bash
cd ~/ASPIRE/aspire/sim && mkdir -p logs
sbatch scripts/tc1/setup/01_probe.sh
```

Between 02 and 03, on the head node: `.venv-libero/bin/hf auth login` (needs gated `facebook/sam3` access).

Session workflow: `sbatch scripts/tc1/setup/04_session.sh` → `squeue -u $USER` → `tail -f logs/error_aspire-session_<id>.err`
for the tunnel line and Jupyter token → from laptop `ssh -L 8891:<node-ip>:8891 yu0001ee@10.96.189.11` →
open `http://127.0.0.1:8891/lab?token=...` → Terminal. `scancel <id>` when done.
