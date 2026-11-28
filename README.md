# pren-software
Software for our autonomous dog robot (HSLU PREN HS26/FS27): voice and gesture recognition, bone search,
and a web 3D simulator to develop and test the robot's brain without hardware.
Python (uv workspace) for the brain and the apps; the web simulator is a separate web app.

## Structure

```
packages/
  dog-protocol/      dog_protocol    data exchanged between web simulator and sim host
apps/
  robot/                             the brain, its own uv workspace (see apps/robot/pyproject.toml)
    dog-core/        dog_core        state machine, states, UART to the Pico
    dog-perception/  dog_perception  object detector (YOLO) and gestures (MediaPipe)
    dog-recorder/    dog_recorder    speech recognition (Vosk)
  sim-host/          dog_sim_host    runs on the laptop: MuJoCo robot, emulated Pico, viewer server
  dog-simulator/                     browser viewer for the simulator, three.js + JSDoc
scenarios/           scenario files for the simulator and tests
config/              settings per run mode
```

The brain is `dog-core`, `dog-perception` and `dog-recorder` in `apps/robot`: the same code runs in the
simulator and on the robot. The root workspace (`uv sync`) holds only `dog-protocol` and the sim host;
the brain's ML libraries live in their own environment, which the simulator uses as `.venv-core`.

Import rules (enforced by `.importlinter` for the root workspace):
- `dog_protocol` does not import the sim host
- the sim host loads the brain at run time (`core_runner.py`), it does not import it

Documentation: [docs/](docs/index.md), served with `uv run --group docs mkdocs serve`
(simulator guide, robot model, Pico protocol, API reference, concepts, decisions).

## Setup

Requires [uv](https://docs.astral.sh/uv/). uv installs Python 3.12 itself.

```sh
uv sync
```

The brain has its own environment in `apps/robot` (`uv sync` there); for the simulator,
`apps/sim-host/scripts/core-env.sh` builds `.venv-core` with the brain and the sim host together.

## Simulator

The simulator runs in two terminals: the **sim host** (physics, emulated Pico, optionally the
real dog core) and the **viewer** in your browser. Install once:

```sh
uv sync
npm --prefix apps/dog-simulator install
```

### 1. Start the sim host, pick one

| You want | Command |
| --- | --- |
| Just the robot, you drive it yourself | `uv run dog-sim` |
| The real dog core, with webcam and microphone | `.venv-core/bin/dog-sim --core` |
| The core, but use the Mac's own camera (an iPhone nearby takes camera 0) | `.venv-core/bin/dog-sim --core --webcam 1` |
| The core without any webcam (no gestures, voice still works) | `.venv-core/bin/dog-sim --core --webcam -1` |

The core needs its own environment. Build it once, and again whenever `dev-core` changes:

```sh
apps/sim-host/scripts/core-env.sh            # core from origin/dev-core
apps/sim-host/scripts/core-env.sh my-branch  # or from another branch
```

### 2. Start the viewer

```sh
npm --prefix apps/dog-simulator run dev
```

Open <http://localhost:5173>.

### 3. Use it

- **Without the core:** hold <kbd>W</kbd> <kbd>A</kbd> <kbd>S</kbd> <kbd>D</kbd> to drive, use the
  posture and Pico buttons, place the bone and the person.
- **With the core:** command the dog like the real one. Say "such" to your laptop's microphone,
  or show a gesture to the webcam. The dog camera shows what the core sees, with its detections;
  the log dock shows every log line of the core, the sim host and the UART.
- **Voice** buttons (such, hier, sitz, platz, auf, brav) give the core a word as if its
  microphone heard it, for when you cannot talk to the laptop.
- **Random bone** puts the bone at a random spot in the search area, turned at random.
- **Light** changes the light of the dog's camera image, the one the core sees: sun strength,
  height and direction, ambient light, presets and random (the viewer's 3D view keeps its own).
- **Reset everything** restarts the sim host and the core. The viewer reconnects after about 5 s.

On first start macOS asks for **camera and microphone permission** for your terminal or IDE.
Allow both, then restart the sim host.

### Troubleshooting

| Problem | Fix |
| --- | --- |
| The viewer says "Sim host offline, retrying" | The sim host is not running, or runs on another port: add `?ws=ws://localhost:PORT` to the viewer URL. |
| The webcam shows your phone | Start with `--webcam 1`. The log names the camera it opened. |
| `No webcam for gestures` in the log | Grant camera permission to your terminal or IDE, then restart. |
| The core is stuck in a state | Click **Reset everything**. |
| `.venv-core/bin/dog-sim` not found | Run `apps/sim-host/scripts/core-env.sh` first. |

More: [docs/simulator/](docs/simulator/index.md), with the core setup in
[core-integration.md](docs/simulator/core-integration.md).

## Detector bench

Scores the core's bone detector on thousands of seeded rendered pictures and compares
versions; one Docker image with a dashboard, for a homelab. See
[docs/simulator/bench.md](docs/simulator/bench.md).

```sh
uv sync --all-packages --extra bench
uv run python -m dog_sim_host.bench run --ref develop -n 200
```

## Commands

```sh
uv run pytest               # tests
uv run ruff check           # lint
uv run ruff format          # format
uv run lint-imports         # check import rules
uv run --group docs mkdocs build --strict        # docs
npm --prefix apps/dog-simulator run typecheck    # viewer JSDoc types
```

CI (`.github/workflows/software-ci.yml`) runs the same checks on every push and pull request.

## Contributing

Branch, commit and PR rules: [CONTRIBUTING.md](CONTRIBUTING.md).
