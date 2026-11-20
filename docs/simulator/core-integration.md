# Core integration

The dog core (state machine, search, return home, command recognition) lives on the
`dev-core` branch. It meets the outside world in two ways, and the simulator covers both.

## 1. UART: no core changes

The core's `Uart` opens a serial port. The simulator creates a virtual one (a pseudo-terminal)
and links it to `/tmp/pren-uart-pi`:

```python
Uart(port="/tmp/pren-uart-pi", logger=logger)
```

Everything behind the port is real core code: `Uart`, `JsonUartProtocol`, `PathToHome`.

**Checked on 2026-11-19** with dev-core's `uart.py`, `uart_protocol.py` and `path_to_home.py`
against the running simulator:

| Step | Core's `PathToHome` reported |
| --- | --- |
| drive 0.1 m/s for 2 s | x = 0.208 m |
| rotate 90° | heading = 88.1° |

## 2. Camera, microphone, models: stand-ins

The states read hardware through objects that `states/startup.py` creates.
`dog_sim_host.core_adapters` has a stand-in for each, offering exactly the calls the states use:

| Core creates | Stand-in | What the core gets |
| --- | --- | --- |
| `cv2.VideoCapture(1)` | `SimCamera` | black 640 × 480 frames at 30 fps (only `frame.shape` is used) |
| `sd.RawInputStream(...)` | `SimMicrophone` | nothing; audio is skipped |
| `ObjectModel()` | `SimObjectModel` | boxes for bone, person and shoes, projected from the world through the dog's camera |
| `GestureModel()` | `SimGestureModel` | the gesture picked in the viewer |
| `AudioModel()` | `SimAudioModel` | the words clicked in the viewer |

`dog_sim_host.core_runner.CoreRunner` swaps these into `dog_core.states.startup` and starts
`PrenMachine` in a background thread (`uv run dog-sim --core`).

!!! note "Shortcut to replace"
    The swap replaces names inside the core's `startup` module, because `startup.enter` builds
    its devices itself. The clean fix is a small change in the core: let `PrenMachine` take its
    devices from outside (about 20 lines), defaulting to the real hardware. Then the runner
    passes the stand-ins and the swap goes away.

## Running it

1. Bring the core into this branch (or this branch into `dev-core`) and install its dependencies.
2. Start `uv run dog-sim --core` and the viewer.
3. Click **such** in the viewer: the core turns 180°, creeps forward and steers to the bone.

The viewer shows the core's current state in the top bar, or the error if it failed to start.

## First full run (2026-11-20)

The complete dev-core core (commit `86b36b8`) ran inside the simulator in its own Python
environment, with its ML dependencies installed next to the simulator:

```bash
uv venv core-venv --python 3.12
uv pip install --python core-venv/bin/python <dev-core>/packages/dog-core <dev-core>/packages/dog-perception <dev-core>/packages/dog-recorder -e packages/dog-protocol mujoco websockets
uv pip install --python core-venv/bin/python --no-deps -e packages/dog-behavior -e apps/sim-host
core-venv/bin/dog-sim --core
```

Startup, `standing_idle`, voice commands, `platz`, `auf` and the 180° turn of `such` all worked.
Then the search saw the bone and drove towards it, but **the bone left the bottom of the
image without counting as close**: it stayed 0.1 of the image width off centre, just outside
the core's 0.08 tolerance, and the steering (`error * 30` degrees) did not centre it in time.
After that the core sends `stop` forever: the state only times out while it has never seen the
bone. Both are core behaviour to look at (steering gain, a timeout after losing the bone);
the simulator's assumption about `angle` (bicycle steering) also plays in.

## Not covered yet

- **Real images for the real models**: YOLO and MediaPipe run on camera frames, but the frames are
  black. The next step: render the dog's camera view and send it to `SimCamera`.
- **The full core on this branch**: it runs only in a separate environment (above) until the
  branches are merged.
- **Import rules**: dev-core's `dog_core` imports OpenCV and the perception packages, which the
  rules on `develop` forbid. That needs sorting out when the branches are merged.
