# Dev log

One entry per iteration: what changed, what we learned, what is next. Newest first.

## 2026-11-28 · Detector bench

- `dog_sim_host.bench` scores the core's bone detector on seeded rendered pictures (distance,
  angle, bone turn, light, floor, a person, camera faults) and compares versions on the same
  pictures. One Docker image with a dashboard, a queue and a GitHub watch, for Coolify.
- The picture code moved from `make_dataset.py` into `dog_sim_host.photos`, shared by both.
- First numbers, 300 trials: the core's current model finds the bone in 3 % of the rendered
  pictures, the model trained on real and rendered frames in 96 %.
- Learned: changing a MuJoCo light in the model needs `mj_forward` before rendering, or the
  picture shows the light from before.

## 2026-11-28 · Test controls in the viewer, real photos for the detector

- Voice buttons give the core a command word without a microphone; it is taken only when the
  core's state allows it, like a heard word.
- Random bone (a random spot in the search area, at least 15 cm from the tape, any turn) and a
  light panel for the core's camera image: building blocks for automatic test runs.
- `prelabel_photos.py` pre-labels real frames with YOLOE-26L, `evaluate_detector.py` measures
  a detector the way the core runs it. A model trained on 315 real and 909 rendered frames
  finds the bone in 73 of 73 held-out real frames; the core's current one in 29.
- Learned: YOLO26 has no NMS and gives each box one class, so prompting bone and person in one
  pass labels the bone a person; one pass per group fixes it.

## 2026-11-27 · Playing field to spec, real floor

- The field now follows the task drawing (Abbildung 3): closed interaction circle of 1.5 m
  radius, 30° search segment from the circle to 5 m with the far arc taped, pylons on its far
  corners 2588 mm apart. Tape is 2 cm wide (photos), not 5 cm.
- The floor is the field's grey slate-look linoleum from photos: cloudy veins, speckle, long
  curved scratches, small pits. It tiles every 1 m (`texuniform`), not 0.6 m.

## 2026-11-27 · Training data for the bone detector

- `scripts/make_dataset.py` renders labelled YOLO images of the bone: random floor, light,
  bone pose and camera pose, labels from the segmentation render, 15 % without bone.
  See [Training data](training-data.md).
- Next: real videos of the bone on the field as a test set, then train and compare
  real only, sim only, and sim + real.

## 2026-11-20 · The viewer as a working tool

- New layout, light theme as PRODUCT.md asks, in a race-timing look: a run clock started by
  SUCH with one split per phase, scene and dog camera side by side (the camera as large as it
  fits), the user's webcam in the rail, and an IDE-style log dock with every log line of the
  core, the sim host and the UART, filterable and searchable.
- The sim host now streams the webcam image and all logs to the viewer.

## 2026-11-20 · dev-core moved to apps/robot

- dev-core `d73d7e7` moved the core packages from `packages/` to `apps/robot/` and cleaned up
  formatting; no behaviour change for the simulator. `core-env.sh` now takes either layout.
  The core starts in the simulator as before.

## 2026-11-20 · The core runs with its own models

- With `--core` the simulator replaces only hardware: the dog's camera is rendered by MuJoCo,
  gestures come from the laptop webcam, voice from the laptop microphone. The stand-ins for
  YOLO, the gesture model and Vosk, and the viewer's speak and gesture buttons, are gone.
- `scripts/core-env.sh` builds `.venv-core` with the core from `origin/dev-core`, unchanged.
- The bone is the scan of the real bone (`Knochen.stl`, 289 × 102 × 61 mm), laid flat and
  reduced to 4,000 triangles by `scripts/prepare_bone.py`.
- Bone and room made realistic: 21 cm white bone, room light, and the competition floor
  (terracotta tiles, light grout, from photos). On light-grey tiles the core's YOLO found the
  bone in 49 % of rendered views; on the terracotta floor in none. The light grout lines are
  the cause. `scripts/detect_photos.py` runs the detector on real photos to check the real floor.
- The playing field from a photo: dark glossy linoleum, white tape, interaction circle of
  1.5 m radius open towards the search area, two lines to the pylons at 5 m. On it the core's
  detector finds the rendered bone in 1 of 72 views. Vosk crashes if loaded after MediaPipe.

## 2026-11-20 · Interface definition checked

- Compared the team's UART interface definition (2026-11-13) with dev-core and the simulator:
  they still use the older protocol. Differences and results in [Interface definition](interface.md).
- Added the `vorderbeine_runter` pose for the bone approach.
- The Pico emulator speaks the definition's protocol next to the old one: `wheels`, `pose`,
  and a 50 Hz `measurements` packet with raw values. dev-core's old code still works on the
  same port. A malformed UART command no longer stops the simulator.
- Learned: the proposed 50 Hz JSON packet needs 17.5 kB/s, more than 115200 baud carries.
- Learned: the chest ultrasonic sensor does not see the bone, and with the front legs down the
  snout stays 226 mm above the floor, so the dog drives over the bone.

## 2026-11-19 · Iteration 2: legs from the CAD parts

**Built**

- The hardware team's STL files (Grundkörper, Antriebsstütze, linkage, Bein, Rad) are now the
  legs. Each leg is the test setup's four-bar linkage, with real hole distances, 20 mm wheels
  and masses from the part volumes.
- `scripts/build_legs.py` generates the legs from the hole positions, so a CAD change is one
  edit and one command.
- The viewer draws CAD meshes: the sim host sends each mesh once in the scene message.
- Postures re-tuned: positive servo angle now lowers the body; `platz` lowers all four legs.

**Learned** (details in [robot model findings](robot-model.md#findings-so-far))

- The linkage is nearly a parallelogram, so the legs stay upright and the body moves
  75 mm between `auf` and `platz`.
- Without springs the front servos hold half their stall torque standing.
- A large unramped servo jump can snap a leg into its crossed pose; a knee stop prevents it.
- MuJoCo takes mesh mass from the convex hull unless told otherwise (`inertia="exact"`);
  with holes in every part that was 35% too heavy.

**Next**

- Confirm with the hardware team: servo shaft position, which bar goes to which leg hole,
  spring hooks, Zugfeder rate and length, rear wheel design, part material.
- STLs for torso and head once they exist.

## 2026-11-19 · Iteration 1: MuJoCo simulator with browser viewer

**Built**

- Robot model in MuJoCo from the flipchart drawing and the CAD part names. Splayed legs, each
  driven by a servo through a crank and a linkage bar, with tension springs. Driven front wheels,
  rear casters, head and tail servos, camera, IMU, encoders, ultrasonic sensor.
- Pico emulator speaking the core's UART JSON protocol over a virtual serial port.
- Stand-ins for camera, microphone and recognition models, and a runner that starts the real
  core with them.
- Browser viewer (three.js): 3D view, dog's camera with detection boxes, joint torques, springs,
  sensors, UART log, manual driving.
- These docs (MkDocs Material) and ADR 3.

**Learned** (details in [robot model findings](robot-model.md#findings-so-far))

- Rear legs must fold backwards, and stronger servos can tip the dog over.
- Wheels must coast while the legs move, or the servos stall.
- Springs cut the standing servo load from 0.48 to 0.19 Nm.
- The camera needs to tilt down and sit clear of the snout.
- The core's real UART and odometry code works against the simulator unchanged. This also caught
  a framing bug in the simulator's serial port (fixed).

**Next**

- Real dimensions from the CAD model; STL meshes instead of simple shapes.
- Agree with the firmware side what `drive`'s `angle` means.
- Let the core take its devices from outside, then run the full core here.
- Render camera frames so the real YOLO and gesture models can run on them.
- Scenario files (`scenarios/`) for repeatable search runs.
