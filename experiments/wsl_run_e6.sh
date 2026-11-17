#!/usr/bin/env bash
# Like wsl_run.sh, but in the separate E6 environment (~/.venvs/mosquito-explore-e6), which adds
# torch_geometric plus torch_scatter / torch_cluster wheels built for torch 2.11 + cu126.
set -euo pipefail
commit=$(git rev-parse HEAD)
mod=$1; shift
wsl -e bash -c "export EXP_GIT_COMMIT=$commit; cd /mnt/c/repos/mosquito-cfd/.claude/worktrees/explore-surrogate-experiments && PYTHONPATH=.:src \$HOME/.venvs/mosquito-explore-e6/bin/python -m $mod $*" 2>&1 | grep -v 'fstab'
