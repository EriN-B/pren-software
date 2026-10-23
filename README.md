# pren-software
Software for our autonomous dog robot (HSLU PREN HS26/FS27): voice and gesture recognition, bone search, and a 2D simulator. Python, uv workspace.

## Structure

```
packages/
  dog-core/        dog_core        messages, ports, clock (standard library only)
  dog-perception/  dog_perception  recognisers (depends on dog_core)
  dog-recorder/    dog_recorder    recording (depends on dog_core)
apps/
  sim/             dog_sim         2D simulator
  robot/           dog_robot       code that runs on the robot
models/            model files (gitignored), listed in manifest.yaml
```

Import rules (enforced by `.importlinter`):
- `dog_core` imports only the standard library
- `dog_perception` and `dog_recorder` import only `dog_core`, not each other
- apps do not import each other

## Setup

Requires [uv](https://docs.astral.sh/uv/). uv installs Python 3.12 itself.

```sh
uv sync
```

Model dependencies are extras of `dog-perception`, install only what you need:

```sh
uv sync --all-packages --extra vosk   # also: mediapipe, yolo
```

## Commands

```sh
uv run pytest               # tests
uv run ruff check           # lint
uv run ruff format          # format
uv run lint-imports         # check import rules
```

CI (`.github/workflows/software-ci.yml`) runs the same checks on every push and pull request.

## Contributing

Branch, commit and PR rules: [CONTRIBUTING.md](CONTRIBUTING.md).
