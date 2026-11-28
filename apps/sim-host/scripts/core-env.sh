#!/usr/bin/env bash
# Builds .venv-core: the simulator plus the real dog core, taken unchanged from a git ref.
#
#   apps/sim-host/scripts/core-env.sh            # core from origin/dev-core
#   apps/sim-host/scripts/core-env.sh my-branch  # or any other ref
#   .venv-core/bin/dog-sim --core
#
# The core's packages need ML libraries (mediapipe, ultralytics, vosk, OpenCV) that this
# branch does not install, so they live in their own environment. Rerun after core changes.
set -euo pipefail

ref=${1:-origin/dev-core}
root=$(git rev-parse --show-toplevel)
cd "$root"
git fetch -q origin 2>/dev/null || true

# Where the core lives on that ref: apps/robot since 2026-11-20, packages before.
core=packages
if git cat-file -e "$ref:apps/robot/dog-core" 2>/dev/null; then core=apps/robot; fi

rm -rf .core && mkdir .core
# The whole folder: the core packages refer to each other as a uv workspace.
git archive "$ref" "$core" | tar -x -C .core

uv venv -q --allow-existing --python 3.12 .venv-core
py=.venv-core/bin/python
# The core's own packages first, so the stub dog-core of this branch never gets in.
uv pip install -q --python "$py" --reinstall-package dog-core --reinstall-package dog-perception \
  --reinstall-package dog-recorder \
  ".core/$core/dog-core" ".core/$core/dog-perception" ".core/$core/dog-recorder" \
  -e packages/dog-protocol "mujoco>=4.0.1" "websockets>=17.3" ncnn  # ncnn: YOLO model format
uv pip install -q --python "$py" --no-deps -e apps/sim-host

echo "Core from $ref ($(git rev-parse --short "$ref")) ready: .venv-core/bin/dog-sim --core"
