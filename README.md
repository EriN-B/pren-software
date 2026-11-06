# pren-software
Software for our autonomous dog robot (HSLU PREN HS26/FS27): voice and gesture recognition, bone search,
and a web 3D simulator to develop and test the robot's brain without hardware.
Python (uv workspace) for the brain and the apps; the web simulator is a separate web app.

## Structure

```
packages/
  dog-core/        dog_core        messages, ports, clock (standard library only)
  dog-behavior/    dog_behavior    behaviour state machine (depends on dog_core)
  dog-perception/  dog_perception  recognisers (depends on dog_core)
  dog-recorder/    dog_recorder    recording (depends on dog_core)
  dog-protocol/    dog_protocol    data exchanged between web simulator and sim host
apps/
  robot/           dog_robot       runs on the robot: brain + hardware adapters
  sim-host/        dog_sim_host    runs on the laptop: brain + simulator adapter
  dog-simulator/                   web 3D simulator (not started)
scenarios/         scenario files for the simulator and tests
config/            settings per run mode
models/            model files (gitignored), listed in manifest.yaml
```

The brain is `dog-core`, `dog-behavior`, `dog-perception` and `dog-recorder`: the same code runs in the
simulator and on the robot. Only the adapters in the apps differ.

Import rules (enforced by `.importlinter`):
- `dog_core` imports only the standard library
- `dog_behavior`, `dog_perception` and `dog_recorder` import only `dog_core`, not each other
- the brain does not import `dog_protocol`; `dog_protocol` does not import the brain or the apps
- apps do not import each other

Decisions: [docs/adr/](docs/adr/).

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
