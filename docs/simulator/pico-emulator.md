# Pico emulator

`dog_sim_host.pico.PicoFirmware` does in simulation what the Raspberry Pi Pico 2 firmware does
on the robot: it takes the Pi 4's UART commands, drives the servos and the H-bridge, and reports
odometry back. It doubles as a **reference for the real firmware**: the behaviour below is what
the core expects.

## Wire format

One JSON object per line, ASCII, 115200 baud 8N1, matching `JsonUartProtocol` in
`dog_core/uart_protocol.py` (dev-core branch).

### Pi 4 → Pico

| Message | Effect |
| --- | --- |
| `{"command":"drive","speed":0.1,"angle":0}` | drive at `speed` m/s with steering `angle` degrees; **expires after 0.5 s** unless renewed |
| `{"command":"rotate","degrees":90}` | turn in place by that much, clockwise positive, using the IMU heading |
| `{"command":"stop"}` | stop driving and turning |
| `{"command":"auf"}`, `"sitz"`, `"platz"` | move the leg servos to that [posture](robot-model.md#postures) |
| `{"command":"brav"}` | wag the tail for 2 s |
| `{"command":"signal_found"}` | shake the head for 2 s |

### Pico → Pi 4, every 50 ms

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
python3 -c "import os; f=os.open('/tmp/pren-uart-pi', os.O_RDWR); os.write(f, b'{\"command\":\"sitz\"}\n')"
```
