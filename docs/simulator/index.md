# Simulator overview

The simulator replaces the robot's **body and world** so the **brain** (the dog core) can be
developed and tested on a laptop. The core cannot tell the difference: it talks to the same
serial port protocol and reads camera, microphone and recognition results through the same calls.

![Simulator showing the dog in its standing pose](images/viewer.jpg){ loading=lazy }

## Run it

Two terminals, from the repo root:

```bash
uv run dog-sim
```

```bash
npm --prefix apps/dog-simulator install && npm --prefix apps/dog-simulator run dev
```

Open <http://localhost:5173>. Drive with **W A S D**, try the posture buttons, drag the view.
With the dog core installed (dev-core branch), add `--core` to let it control the dog.

| Option | Default | Meaning |
| --- | --- | --- |
| `--port` | `8780` | WebSocket port the viewer connects to |
| `--link` | `/tmp/pren-uart-pi` | symlink to the virtual serial port the core opens |
| `--core` | off | also run the dog core inside the simulator |

## How it fits together

```mermaid
flowchart LR
    subgraph host["sim-host (Python, one process)"]
        world["World<br/>MuJoCo physics"]
        pico["PicoFirmware<br/>emulated Pico 2"]
        adapters["core_adapters<br/>camera, mic, models"]
        core["dog core<br/>(optional, --core)"]
    end
    viewer["Browser viewer<br/>three.js"]

    core -- "UART JSON lines<br/>virtual serial port" --> pico
    pico -- "odometry 20 Hz" --> core
    pico -- "servo + wheel targets" --> world
    world -- "encoders, IMU" --> pico
    world -- "object positions" --> adapters
    adapters -- "boxes, words, gestures" --> core
    world -- "poses, joints, springs 30 Hz" --> viewer
    viewer -- "commands, place, reset" --> host
```

| Part | Real robot | Simulator |
| --- | --- | --- |
| Body, motors, sensors | hardware | [MuJoCo model](robot-model.md) |
| Pico 2 firmware | C on the Pico | [`PicoFirmware`](pico-emulator.md) |
| UART cable | `/dev/serial0` | pseudo-terminal at `/tmp/pren-uart-pi` |
| Camera + YOLO | Pi camera, `ObjectModel` | boxes projected from the world |
| Microphone + Vosk | USB mic, `AudioModel` | words clicked in the viewer |
| Hand gestures | camera, `GestureModel` | gesture picked in the viewer |

## What runs where

- `apps/sim-host`: Python package `dog_sim_host`. Physics, Pico emulator, serial port, WebSocket server.
- `apps/dog-simulator`: the browser viewer (Vite + three.js). It only draws; it simulates nothing.
- `packages/dog-protocol`: the WebSocket messages between the two.

Checks: `uv run pytest apps/sim-host` (physics, Pico, serial link, camera projection) and
`npm --prefix apps/dog-simulator run typecheck`.
