# Robot model

The robot is described in MJCF, MuJoCo's XML format:

- `apps/sim-host/src/dog_sim_host/assets/dog.xml`: the robot
- `apps/sim-host/src/dog_sim_host/assets/scene.xml`: floor, home spot, bone and person; includes `dog.xml`

Axes: **x forwards, y to the dog's left, z up**. Units: metres, kilograms, radians.
The dog starts at home (the origin) facing +x.

!!! warning "Placeholder numbers"
    Dimensions and masses come from the flipchart drawing and the part names of the CAD test
    setup, not from measured parts. Replace them as the mechanical design firms up; every value
    used is listed below. After a change, run `uv run pytest apps/sim-host` and update this page.

## From the drawing to the model

| Drawing / CAD part | In `dog.xml` | Notes |
| --- | --- | --- |
| Grundkörper (body) | `torso` box 0.40 × 0.18 × 0.14 m, 2.0 kg | Emergency stop ("Not") and speaker ("Woof!") are decoration |
| Kopf + Servo-Kopf | `head` body, `neck` hinge (z axis), position servo 0.4 Nm | Carries the camera, ears, LED matrix |
| Kamera-Modul | `eye` camera on top of the snout, 48.8° vertical field of view, tilted 20° down | Pi camera v2 |
| Servo-Schwanz | `tail` hinge, position servo 0.2 Nm | Wags on `brav` |
| Bein (×4) | `leg_*` capsule on the passive `hip_*` hinge (Achse_Grundkörper) | Splayed 0.3 rad from vertical, as drawn |
| MG946R (Servo-Beine 4x) | `servo_*` hinge + position actuator `hip_*`, 1.3 Nm, kp 25 | Drives the leg through the linkage |
| linkage (+ Achse_linkage) | `crank_*` (0.07 m) and `linkage_*` (0.045 m) bars | Parallelogram: leg angle = servo angle |
| Zugfeder | `spring_*` tendons, 150 N/m, pull above 0.14 m | Carry part of the weight |
| Antriebsstütze, Achse_Rad, Motor | `wheel_left` / `wheel_right` on the front legs, r = 0.05 m | Velocity actuators, 0.6 Nm |
| Rear wheels | frictionless `caster_rear_*` balls, r = 0.02 m | Rear legs are longer so the body stands level |
| Encoder links/rechts | `encoder_left` / `encoder_right` sensors on the wheel joints | Distance = angle × radius |
| IMU | `imu_orientation`, `imu_gyro`, `imu_accel` on the `imu` site | Heading reported clockwise |
| Ultraschallsensor | `sonar` rangefinder on the chest | Shown in the viewer only; the core does not use it yet |

### The leg mechanism

```
   body ──●── hip axle (passive)            ● = hinge
          │╲
          │ ╲  servo shaft (MG946R) ●──crank──●
     leg  │  ╲                       linkage  │
          │   ●───────────────────────────────┘   pinned to the leg (equality "connect")
          │
       wheel / caster
```

Each leg is a closed loop: the servo turns the crank, the linkage bar passes the motion on to
the leg. Crank and leg are the same length up to the attachment point, so the four bars form a
parallelogram and **the servo angle equals the leg angle**. A different crank length would give
the servo leverage. That is the first thing to change once the real CAD dimensions are in.

## Postures

Servo angles relative to the drawing pose (`auf` = 0); positive swings the foot backwards.
They live in `pico.py` (`POSTURES`).

| Posture | Front | Rear | Body height | Servo load (of 1.3 Nm) |
| --- | --- | --- | --- | --- |
| `auf` | 0 | 0 | 0.27 m | 0.19 Nm |
| `sitz` | 0 | +0.7 | rear lowered, nose up | 0.53 Nm |
| `platz` | −0.6 | +0.6 | 0.19 m | 0.79 Nm |

## Findings so far

The model is rough, but these come from the mechanics, not from the numbers:

1. **Fold the rear legs backwards.** With the rear feet swinging forwards under the body, 1.5 Nm
   servos could not lift the dog out of `sitz`, and 2.5 Nm servos lifted it so hard it tipped
   over onto its tail.
2. **Stronger is not automatically better.** With 2.5 Nm servos, going from `platz` to `auf`
   flipped the first model nose-down.
3. **Let the wheels coast while the legs move.** When the legs spread, the wheels have to roll.
   With the H-bridge braking (speed 0), the servos stall at 1.3 Nm and the dog collapses. The
   emulated Pico now coasts while the leg servos move and brakes otherwise.
4. **Tension springs halve the servo load.** Standing without springs: 0.48 Nm per front servo.
   With 150 N/m springs: 0.19 Nm.
5. **Turning in place pivots around the driven front axle**, not the body centre. The body
   swings about 0.2 m sideways during a 90° turn.
6. **A camera looking straight ahead misses the floor near the dog.** At 0.41 m height it sees
   the floor only from 1.2 m ahead, so the search would lose the bone long before reaching it.
   Tilted 20° down, it sees from about 0.3 m. In the eye socket, the snout hid a quarter of the image.

## Changing the model

- Open `dog.xml` in MuJoCo's own viewer to look at it alone: `uv run python -m mujoco.viewer --mjcf apps/sim-host/src/dog_sim_host/assets/scene.xml`.
- Every geom is drawn by the browser automatically. New parts need no viewer change.
- Wheel radius, track width and wheelbase are read from the model by the Pico emulator.
- Once STL files of the parts are in the repo, they can replace the simple shapes as MuJoCo meshes.
