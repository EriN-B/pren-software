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

## Not covered yet

- **Real images for the real models**: YOLO and MediaPipe run on camera frames, but the frames are
  black. The next step: render the dog's camera view and send it to `SimCamera`.
- **Running the full core here**: its ML dependencies (mediapipe, ultralytics, vosk) are not installed
  on this branch, so only the UART path was run against the real core code.
- **Import rules**: dev-core's `dog_core` imports OpenCV and the perception packages, which the
  rules on `develop` forbid. That needs sorting out when the branches are merged.
