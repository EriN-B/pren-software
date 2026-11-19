# Dev log

One entry per iteration: what changed, what we learned, what is next. Newest first.

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
