# Pico emulator

`dog_sim_host.pico.PicoFirmware` does in simulation what the Raspberry Pi Pico 2 firmware does
on the robot: it takes the Pi 4's UART commands, drives the servos and the H-bridge, and reports
sensor values back. It doubles as a **reference for the real firmware**: the behaviour below is what
the core expects.

## Wire format

One JSON object per line, ASCII, 115200 baud 8N1, matching `JsonUartProtocol` in
`dog_core/uart_protocol.py` (dev-core branch).

The emulator speaks **two protocols on the same port**:

- **new**: the [interface definition](interface.md) of 2026-11-13. Raw data up, commands down;
  the Pico interprets nothing. Message and field names are the simulator's proposal.
- **old**: what the core on dev-core speaks today. Kept until the core moves over.

A message with a missing or wrong field is logged and ignored; it never stops the simulator.

### Pi 4 → Pico, new

| Message | Effect |
| --- | --- |
| `{"command":"wheels","left_mm_s":100,"right_mm_s":100}` | target speed per wheel, forwards positive; send about every 50 ms, **expires after 0.5 s** |
| `{"command":"pose","pose":"VORDERBEINE_RUNTER"}` | move the leg servos to a pose: `STEHEN`, `SITZ`, `PLATZ`, `VORDERBEINE_RUNTER` |

Turning is the Pi's job: different wheel speeds, checked against the gyro.

### Pico → Pi 4, new, every 20 ms

```json
{"type":"measurements","timestamp":19.008,"distance_mm":706,
 "accel_m_s2":[-2.01,0.0,9.6],"gyro_deg_s":[0.0,0.0,0.0],
 "encoder_left":{"rpm":46.2,"angle_deg":554.3},"encoder_right":{"rpm":46.2,"angle_deg":554.3},
 "servos_deg":{"hip_front_left":43.0,"hip_front_right":43.0,"hip_rear_left":0.0,"hip_rear_right":0.0,"neck":0.0,"tail":0.0},
 "emergency_stop":false}
```

(one line on the wire)

| Field | Meaning |
| --- | --- |
| `timestamp` | seconds, strictly increasing |
| `distance_mm` | ultrasonic distance; `null` when nothing is within 4 m |
| `accel_m_s2` | acceleration including gravity (about 9.81 up at rest), torso axes: x forwards, y left, z up |
| `gyro_deg_s` | rotation rate about the same axes |
| `encoder_*` | wheel speed in rpm and running angle in degrees, forwards positive; distance = angle in rad × 20 mm |
| `servos_deg` | **last commanded** angle per servo; hobby servos do not report their real position |
| `emergency_stop` | Not-Aus pressed; the Pico stops the wheels by itself |

!!! warning "Does not fit on the wire yet"
    One packet is about 350 bytes. At 50 Hz that is 17.5 kB/s, but 115200 baud carries only
    11.5 kB/s. The real link needs a higher baud rate (the Pi and the Pico manage 921600),
    a binary format or shorter keys, or a lower rate. The simulator's virtual port has no
    such limit, so it will not catch this.

### Pi 4 → Pico, old

| Message | Effect |
| --- | --- |
| `{"command":"drive","speed":0.1,"angle":0}` | drive at `speed` m/s with steering `angle` degrees; **expires after 0.5 s** unless renewed |
| `{"command":"rotate","degrees":90}` | turn in place by that much, clockwise positive, using the IMU heading |
| `{"command":"stop"}` | stop driving and turning |
| `{"command":"auf"}`, `"sitz"`, `"platz"`, `"vorderbeine_runter"` | move the leg servos to that [posture](robot-model.md#postures) |
| `{"command":"brav"}` | wag the tail for 2 s |
| `{"command":"signal_found"}` | shake the head for 2 s |

### Pico → Pi 4, old, every 50 ms

```json
{"type":"odometry","timestamp":12.35,"left_distance_m":0.412,"right_distance_m":0.398,"heading_deg":17.2}
```

- `timestamp`: seconds, strictly increasing (also across a simulator reset)
- `*_distance_m`: total wheel travel since start, forwards positive
- `heading_deg`: IMU yaw, **clockwise**, 0–360

The core stops trusting its home tracking if no odometry arrives for 1 s.

## Behaviour the firmware team should check

| Topic | What the emulator does | Status |
| --- | --- | --- |
| Meaning of `angle` | steering angle of a bicycle with the wheel-to-caster wheelbase: turn rate = speed · tan(angle) / wheelbase | **assumption, to agree** |
| Turn speed for `rotate` | 90°/s, slowing over the last degrees, done within 2° | assumption |
| Drive timeout | 0.5 s, then stop | proposal |
| Servo speed | 4 rad/s (MG946R class) | from datasheet class |
| H-bridge when idle | **brake** (hold speed 0); **coast** while the leg servos move | needed, see finding 3 in the robot model |
| Emergency stop | wheels braked, motion commands ignored until released | matches the "Not-Aus" input |

## Talking to it by hand

With the simulator running, any serial tool can play the core:

```bash
python3 -c "import os; f=os.open('/tmp/pren-uart-pi', os.O_RDWR); os.write(f, b'{\"command\":\"pose\",\"pose\":\"SITZ\"}\n')"
```
