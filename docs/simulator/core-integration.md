# Core integration

The dog core (state machine, search, return home, command recognition) lives on the
`dev-core` branch. With `--core` the simulator runs it **unchanged, models included**: YOLO
looks for the bone and the person, MediaPipe and the kNN classifier read hand gestures, Vosk
listens for words. The simulator only replaces the hardware.

| Core opens | On the robot | In the simulator |
| --- | --- | --- |
| `cv2.VideoCapture` | Pi camera | `SimCamera`: the dog's camera rendered by MuJoCo (640 × 480, 30 fps); the gesture thread gets the **laptop webcam** instead |
| `sd.RawInputStream` | USB microphone | the **laptop microphone**, untouched |
| serial port | `/dev/serial0` to the Pico | virtual serial port of the [Pico emulator](pico-emulator.md) |

So you command the dog like the real one: say "such" to your laptop, or show a gesture to its
webcam.

## Running it

The core needs ML libraries this branch does not install, so it gets its own environment,
built from a git ref (default `origin/dev-core`) without changing the core:

```bash
apps/sim-host/scripts/core-env.sh
```

```bash
.venv-core/bin/dog-sim --core
```

Then start the viewer as usual. The top bar shows the core's state. Rerun `core-env.sh` after
the core changes. It finds the core in `apps/robot` (dev-core since `d73d7e7`) or in
`packages` (before).

**reset** in the viewer restarts the whole sim host, world, Pico and core, because the core's
states run in their own threads and cannot be reset from outside. The viewer reconnects after
about 5 s; the core is back in `standing_idle`. This also gets the core out of a stuck state.

| Option | Default | Meaning |
| --- | --- | --- |
| `--webcam` | `0` | laptop camera for gestures; `-1` gives the gesture thread the dog's view instead |

With an iPhone nearby, macOS may list it as camera 0 (Continuity Camera) and the Mac's own
camera as 1: then start with `--webcam 1`. The log names the opened camera and its size, and
the green light next to the Mac's camera shows which one is in use.

macOS asks for **camera and microphone permission** for the app that starts the simulator
(Terminal, your IDE). Without camera permission the log says `No webcam for gestures` and
gestures cannot work; voice still does.

## How the camera is split

The core reads one camera for two jobs: the states (searching, hier) look for objects, the
gesture thread looks for hands. A rendered world has no hand in it, so `SimCamera` hands each
reader its own image by the reading thread's name: `Gesture recognition` gets the webcam,
everyone else the dog's view.

!!! note "Shortcuts to replace"
    - The thread name comes from `dog_core.command_recognition`. If the core renames the
      thread, gestures see the dog's view and stop working.
    - The simulator swaps the camera and the serial port by replacing names inside the core's
      `startup` module, because `startup.enter` builds its devices itself. Cleaner: the core
      takes its camera and port from outside, defaulting to the real hardware.

## Findings for the core team

Checked on 2026-11-20 with dev-core `a9a00b9`.

**On the real playing field the detector does not find the bone in rendered images.** Measured
with the core's YOLO: 6 distances (0.6 to 2 m from the camera) × 3 sideways offsets × 4 bone
angles, bone fully in view.

| Scene | Found |
| --- | --- |
| scanned bone (29 cm, cream), dark green checker floor | 2 of 72 (3 %) |
| 21 cm white bone, light-grey 15 cm tiles with darker joints | 35 of 72 (49 %) |
| 21 cm white bone, flat-coloured floor | 0 of 72 |
| 21 cm white bone, terracotta 30 cm tiles with light grout (canteen photos) | 0 of 72 |
| **now: the playing field (photo, 2026-11-20): dark glossy linoleum, white tape** | **1 of 72** |
| same, matte or without scratches | 0–1 of 72 |
| terracotta without grout / with dark grout | 20 of 72 (28 %) each |
| terracotta with mid-dark grout | 7 of 72 (10 %) |

On terracotta, light grout lines about as bright as the white bone stop the detector. On the
dark linoleum of the real field it finds nothing either, glossy or matte, scratched or not. It
worked well only on light-grey tiles. Whether this also happens on the real floor or only in the
render (perfect, sharp joints) only real photos can tell: **photograph the real bone on the
real floor** and run the core's detector on the photos:

```bash
.venv-core/bin/python apps/sim-host/scripts/detect_photos.py photos/*.jpg
```

It prints what the detector finds and writes copies with the boxes drawn in. On the floor
photos without a bone it found nothing (no false alarms). If the real photos fail too, the
detector needs training images on this floor; that is perception work, not simulator work.

**One missed frame stops the search.** `searching` stops the dog whenever the bone is missing
in a frame, and if it stays missing before counting as close, the state sends `stop` forever:
its timeout only runs before the bone was first seen. With a flickering detector (in the
simulator now, on the real robot with changing light) the search should tolerate a few missed
frames and have a way out after losing the bone.

**Model load order matters.** Loading Vosk after MediaPipe crashes the process (segmentation
fault) on macOS. The core's `startup` loads Vosk first, so it works; keep that order.

**Voice works from the laptop microphone**: Vosk transcribed room speech right after startup.
