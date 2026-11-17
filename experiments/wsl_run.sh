#!/usr/bin/env bash
# Run an experiment module on the A5000 inside WSL2:  experiments/wsl_run.sh experiments.e1_hover_gate.run --stage train
# Passes the commit in, because git cannot resolve this Windows worktree from WSL (#78).
set -euo pipefail
commit=$(git rev-parse HEAD)
mod=$1; shift
wsl -e bash -c "export PATH=\$HOME/.local/bin:\$PATH UV_PROJECT_ENVIRONMENT=\$HOME/.venvs/mosquito-cfd-train EXP_GIT_COMMIT=$commit; cd /mnt/c/repos/mosquito-cfd/.claude/worktrees/explore-surrogate-experiments && uv run --frozen --group train python -m $mod $*" 2>&1 | grep -v 'fstab'
