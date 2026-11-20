# Dev log

One entry per iteration: what changed, what we learned, what is next. Newest first.

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
