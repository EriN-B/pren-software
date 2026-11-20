# Interface definition vs. simulator

The team's [UART interface definition of 2026-11-13](../reference/PREN1%20-%202026-11-13%20Schnittstellendefinition.pdf)
(Pi 4 ↔ Pico 2) describes how the wire should work. The dog core on `dev-core` (last change
2026-11-14) still speaks the older protocol. The simulator's Pico emulator now speaks **both**,
on the same serial port, so the core can move over one message at a time. The definition
leaves message names and the packet format open; the simulator's proposal is in the
[Pico emulator wire format](pico-emulator.md#wire-format).

## Differences

Its main rule is **raw data up, commands down: the Pico interprets nothing.** Today the Pico
works out distance and heading, and turns to an angle by itself.

| Topic | Interface definition (simulator: new protocol) | dev-core (simulator: old protocol) |
| --- | --- | --- |
| Driving | target speed left and right in mm/s, about 20 Hz; Pico stops when commands stop | `drive` with `speed` m/s and `angle` degrees; stops after 0.5 s without commands |
| Turning | Pi steers with the two wheel speeds | `rotate` by degrees, the Pico turns using the IMU |
| Servos | position code: poses (STEHEN, SITZ, VORDERBEINE_RUNTER) normally, single angles for testing | posture commands `auf`, `sitz`, `platz`, `vorderbeine_runter` |
| Measurements | one packet with timestamp, about 50 Hz | `odometry` at 20 Hz |
| Encoders | per wheel: speed in rpm and running angle in degrees | left and right distance in m, computed on the Pico |
| IMU | acceleration x, y, z in m/s² (with gravity), rotation rate in °/s | heading in degrees only, computed on the Pico |
| Ultrasonic | distance in mm | not sent (the simulator measures it, the viewer shows it) |
| Servo positions | position per servo (only the last command, hobby servos give no feedback) | not sent |
| Emergency stop | Pico sends its status and stops by itself | not sent; the simulator's Not-Aus stops the wheels |

In the simulator now: `wheels` (mm/s per wheel), `pose` with the pose codes, and the 50 Hz
`measurements` packet with distance, IMU, encoders, servo positions and emergency stop.
Still to agree with the team: the names, single servo angles for testing (not built yet),
and how the emergency stop is reported (now a field in every packet).

**The proposed packet does not fit on the wire at 115200 baud**: about 350 bytes of JSON at
50 Hz is 17.5 kB/s, the link carries 11.5 kB/s. See the
[wire format](pico-emulator.md#wire-format) for options.

## Open questions, tried in the simulator

These use the current, partly placeholder model: legs from CAD, torso and head from the drawing.

**Does the ultrasonic sensor see the bone?** No. Mounted on the chest at 224 mm and looking
straight ahead, its beam passes over the bone at every distance. With the front legs down the
dog tilts 12° nose down and the beam hits the floor about 0.7 m ahead, so it mostly measures
the floor. It saw the bone at only one distance (0.5 m). The simulator models a single ray; a
real sensor's cone of about 15° reaches the floor even sooner. The camera has to stay the main
source, as the definition expects.

**How far does the dog tilt with the front legs down?** 12° nose down at the servo limit.
The torso's lowest edge drops from 189 mm to 110 mm and the camera from 398 mm to 282 mm. The
front servos hold 0.45 Nm (of 1.3 Nm).

**Can the snout touch the bone?** Not with the current head. With the front legs fully down
the lowest point of the snout is still 226 mm above the floor, and the bone fits under the
torso, so the dog drives over it. The leg travel (75 mm) comes from the CAD parts; the head is
still the drawing's box. A snout-first approach needs a head that tilts down or reaches much
lower, or the touch has to be detected differently (button, camera).

**From which distance should the dog lower its legs?** Still open: it needs the core's
approach behaviour. The pose and slow driving in it work (`test_vorderbeine_runter_tilts_nose_down_and_still_drives`).
