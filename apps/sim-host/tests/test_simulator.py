"""Checks the simulated robot behaves like the core expects the real one to."""

import json
import logging
import os
import threading
from types import SimpleNamespace

import numpy as np
import pytest
from dog_sim_host.app import Simulator
from dog_sim_host.core_adapters import GESTURE_THREAD, SimCamera, project
from dog_sim_host.core_runner import CoreRunner
from dog_sim_host.log_buffer import LogBuffer
from dog_sim_host.pico import PicoFirmware
from dog_sim_host.uart_link import PtyLink
from dog_sim_host.world import DETECTABLE, World


@pytest.fixture
def robot():
    world = World()
    pico = PicoFirmware(world)
    world.advance(1.0, pico.control)  # settle onto the floor
    return world, pico


def dog(world):
    return world.data.body("dog").xpos


def test_stands_level(robot):
    world, _ = robot
    assert dog(world)[2] == pytest.approx(0.26, abs=0.01)
    assert abs((world.heading_cw() + 180) % 360 - 180) < 0.5


def test_drive_moves_forward_and_odometry_agrees(robot):
    world, pico = robot
    start_x = dog(world)[0]
    for _ in range(10):  # the core renews drive commands every 0.1 s
        pico.handle({"command": "drive", "speed": 0.1, "angle": 0})
        world.advance(0.1, pico.control)
    travelled = dog(world)[0] - start_x
    odometry = pico.odometry()
    assert travelled == pytest.approx(0.1, abs=0.015)
    assert odometry["left_distance_m"] == pytest.approx(travelled, abs=0.01)
    assert odometry["right_distance_m"] == pytest.approx(travelled, abs=0.01)


def test_drive_expires_without_renewal(robot):
    world, pico = robot
    pico.handle({"command": "drive", "speed": 0.1, "angle": 0})
    world.advance(1.0, pico.control)
    x = dog(world)[0]
    world.advance(1.0, pico.control)
    assert dog(world)[0] == pytest.approx(x, abs=0.005)


def test_positive_steering_turns_clockwise(robot):
    world, pico = robot
    for _ in range(20):
        pico.handle({"command": "drive", "speed": 0.1, "angle": 20})
        world.advance(0.1, pico.control)
    heading = world.heading_cw()
    assert 5 < heading < 90


def axle_centre(world):
    data = world.data
    return (data.body("wheel_left").xpos + data.body("wheel_right").xpos) / 2


def test_rotate_turns_in_place_clockwise(robot):
    world, pico = robot
    start = axle_centre(world).copy()
    pico.handle({"command": "rotate", "degrees": 90})
    world.advance(3.0, pico.control)
    assert world.heading_cw() == pytest.approx(90, abs=4)
    # It pivots around the driven axle, so the torso swings but the axle stays.
    assert axle_centre(world)[:2] == pytest.approx(start[:2], abs=0.03)


def pitch_up(world):
    """How far the torso's nose points up, as the z of its forward axis."""
    return world.data.body("dog").xmat.reshape(3, 3)[2, 0]


def test_sitz_lowers_the_rear_and_loads_the_hips(robot):
    world, pico = robot
    pico.handle({"command": "sitz"})
    world.advance(2.0, pico.control)
    assert pitch_up(world) > 0.1  # nose up, rear down
    rear_hip = world.data.actuator("hip_rear_left").force[0]
    assert 0.1 < abs(rear_hip) < 1.0  # well below the servo's 1.3 Nm


def test_vorderbeine_runter_tilts_nose_down_and_still_drives(robot):
    world, pico = robot
    pico.handle({"command": "vorderbeine_runter"})
    world.advance(2.5, pico.control)
    assert pitch_up(world) < -0.15  # nose down, about 12 degrees
    x = dog(world)[0]
    for _ in range(20):  # the bone approach: slowly forwards
        pico.handle({"command": "drive", "speed": 0.05, "angle": 0})
        world.advance(0.1, pico.control)
    assert dog(world)[0] - x == pytest.approx(0.1, abs=0.03)


@pytest.mark.parametrize("posture", ["sitz", "platz", "vorderbeine_runter"])
def test_stands_back_up_level(robot, posture):
    # Regression: earlier legs stayed down, tipped over, or snapped into the crossed pose.
    world, pico = robot
    pico.handle({"command": posture})
    world.advance(2.5, pico.control)
    pico.handle({"command": "auf"})
    world.advance(3.0, pico.control)
    assert dog(world)[2] == pytest.approx(0.26, abs=0.01)
    assert abs(pitch_up(world)) < 0.05


def test_platz_lowers_the_body_on_closed_leg_linkages(robot):
    world, pico = robot
    pico.handle({"command": "platz"})
    world.advance(2.5, pico.control)
    assert dog(world)[2] < 0.2
    for leg in ("front_left", "front_right", "rear_left", "rear_right"):
        # The four-bar stays closed: drive strut end and leg joint coincide.
        gap = (
            world.data.site(f"crank_end_{leg}").xpos
            - world.data.site(f"leg_attach_{leg}").xpos
        )
        assert max(abs(gap)) < 0.001


def drive_wheels(world, pico, left, right, seconds):
    """Send the interface definition's wheel command at 20 Hz, like the core would."""
    for _ in range(round(seconds / 0.05)):
        pico.handle({"command": "wheels", "left_mm_s": left, "right_mm_s": right})
        world.advance(0.05, pico.control)


def test_wheel_speeds_drive_straight_turn_clockwise_and_expire(robot):
    world, pico = robot
    drive_wheels(world, pico, 100, 100, 1.0)
    assert dog(world)[0] == pytest.approx(0.1, abs=0.015)
    drive_wheels(world, pico, 60, -60, 1.0)  # left faster than right: turn right
    assert 10 < world.heading_cw() < 60
    world.advance(0.6, pico.control)  # no more commands: the Pico stops after 0.5 s
    x = dog(world)[0]
    world.advance(1.0, pico.control)
    assert dog(world)[0] == pytest.approx(x, abs=0.005)


def test_pose_codes_move_the_legs(robot):
    world, pico = robot
    pico.handle({"command": "pose", "pose": "VORDERBEINE_RUNTER"})
    world.advance(2.5, pico.control)
    assert pitch_up(world) < -0.15
    with pytest.raises(KeyError):
        pico.handle({"command": "pose", "pose": "SALTO"})


def test_measurement_packet_has_raw_sensor_values(robot):
    world, pico = robot
    packet = pico.measurements()
    assert packet["accel_m_s2"][2] == pytest.approx(9.81, abs=0.1)  # gravity included
    assert packet["distance_mm"] is None  # nothing within 4 m straight ahead
    world.place("person", dog(world)[0] + 1.0, 0.09)  # one leg straight ahead
    world.advance(0.1, pico.control)
    assert 700 < pico.measurements()["distance_mm"] < 800  # 1 m minus nose and legs
    drive_wheels(world, pico, 100, 100, 0.5)
    packet = pico.measurements()
    assert packet["encoder_left"]["angle_deg"] > 0  # forwards counts up
    assert packet["encoder_left"]["rpm"] == pytest.approx(
        47.7, abs=5
    )  # 100 mm/s, r 20 mm
    pico.handle({"command": "pose", "pose": "SITZ"})
    world.advance(1.0, pico.control)
    servos = pico.measurements()["servos_deg"]
    assert servos["hip_rear_left"] == pytest.approx(
        40.1, abs=0.1
    )  # last command, 0.7 rad
    assert servos["hip_front_left"] == 0


def test_emergency_stop_holds_the_wheels(robot):
    world, pico = robot
    pico.emergency_stop = True
    pico.handle({"command": "drive", "speed": 0.1, "angle": 0})
    x = dog(world)[0]
    world.advance(0.4, pico.control)
    assert dog(world)[0] == pytest.approx(x, abs=0.003)


def test_reset_keeps_odometry_timestamps_increasing(robot):
    _, pico = robot
    before = pico.odometry()["timestamp"]
    pico.reset_with_world()
    assert pico.odometry()["timestamp"] >= before


def test_uart_link_round_trip():
    link = PtyLink(link=None)
    core_end = os.open(link.port, os.O_RDWR | os.O_NOCTTY)
    try:
        os.write(core_end, b'{"command":"stop"}\nnot json\n{"command":"sitz"}\n')
        assert link.read_messages() == [{"command": "stop"}, {"command": "sitz"}]
        link.send({"type": "odometry", "timestamp": 1.0})
        assert json.loads(os.read(core_end, 4096)) == {
            "type": "odometry",
            "timestamp": 1.0,
        }
    finally:
        os.close(core_end)
        link.close()


def test_uart_link_keeps_whole_lines_when_nobody_reads():
    link = PtyLink(link=None)
    for i in range(5000):  # far more than the pty buffer holds
        link.send({"type": "odometry", "timestamp": float(i), "padding": "x" * 40})
    core_end = os.open(link.port, os.O_RDWR | os.O_NOCTTY)
    try:
        first_line = os.read(core_end, 4096).split(b"\n")[0]
        assert json.loads(first_line)["type"] == "odometry"
    finally:
        os.close(core_end)
        link.close()


def test_true_position_of_the_bone_in_the_dogs_image():
    world = World()
    assert project(world.snapshot, DETECTABLE["bone"]) is None  # starts behind
    world.place("bone", 0.8, 0.0)
    x1, _y1, x2, y2 = project(world.snapshot, DETECTABLE["bone"])
    assert (x1 + x2) / 2 == pytest.approx(320, abs=10)  # straight ahead: centred
    assert y2 > 240  # on the floor, below the horizon


def test_core_camera_gives_gestures_the_webcam_and_states_the_world():
    webcam = SimpleNamespace(frame=np.full((480, 640, 3), 1, np.uint8))
    camera = SimCamera(webcam)
    camera.rendered = np.full((480, 640, 3), 2, np.uint8)
    seen = {}

    def read(name):
        seen[name] = int(camera.read()[1][0, 0, 0])

    for name in (GESTURE_THREAD, "searching"):
        thread = threading.Thread(target=read, args=(name,), name=name)
        thread.start()
        thread.join()
    assert seen == {GESTURE_THREAD: 1, "searching": 2}
    assert SimCamera(None).read() == (False, None)  # nothing rendered yet


def test_rendered_camera_shows_the_bone(tmp_path):
    try:
        simulator = Simulator(tmp_path / "uart", with_core=True, webcam=None)
    except Exception as error:  # noqa: BLE001 - no OpenGL, e.g. on a headless CI runner
        pytest.skip(f"cannot render here: {error}")
    try:
        world = simulator.world
        world.place("bone", 0.8, 0.0)
        world.advance(0.1, simulator.pico.control)
        image = simulator.render_camera()
        assert image.shape == (480, 640, 3)
        x1, y1, x2, y2 = (round(v) for v in project(world.snapshot, DETECTABLE["bone"]))
        bone = image[y1:y2, x1:x2].mean()
        floor = image[y1:y2, : max(x1 - 40, 1)].mean()  # same rows, left of the bone
        assert bone > floor + 5  # the white bone is lighter than the light-grey floor
    finally:
        simulator.uart.close()


def test_core_detections_are_read_from_the_cores_log(tmp_path):
    runner = CoreRunner(tmp_path / "uart", webcam=None)
    core_log = logging.getLogger("state_machine")
    core_log.setLevel(logging.INFO)  # as dog_core.states.startup does
    # Exactly how dog_core.states.searching and perform_hier log their boxes.
    core_log.info(
        "Bone bounding box: x1=%.1f, y1=%.1f, x2=%.1f, y2=%.1f, confidence=%.3f",
        *(278.0, 280.0, 362.0, 412.0),
        0.47,
    )
    core_log.info(
        "%s bounding box: x1=1.0, y1=2.0, x2=3.0, y2=4.0, confidence=0.800", "Shoe"
    )
    core_log.info("Currently in state: searching (such)")
    assert runner.detections() == [
        {"label": "bone", "box": [278.0, 280.0, 362.0, 412.0], "confidence": 0.47},
        {"label": "shoe", "box": [1.0, 2.0, 3.0, 4.0], "confidence": 0.8},
    ]


def test_bone_can_be_placed_sideways():
    world = World()
    world.place("bone", 1.0, 0.0, yaw=90)
    world.advance(0.5, lambda: None)
    lengthwise = world.data.body("bone").xmat.reshape(3, 3)[
        :, 0
    ]  # the scan's long side
    assert abs(lengthwise[1]) > 0.99  # now across the dog's view, along y
    height = world.data.body("bone").xpos[2]
    assert height == pytest.approx(0.022, abs=0.004)  # still lying flat


def test_log_buffer_collects_core_uart_and_sim_lines():
    buffer = LogBuffer()
    buffer.attach()
    try:
        core = logging.getLogger("state_machine")
        core.setLevel(logging.INFO)  # as dog_core.states.startup does
        core.info("Currently in state: %s", "searching")
        logging.getLogger("dog_sim_host.uart").info('{"command":"stop"}')
        logging.getLogger("dog_sim_host").warning("Pico ignores bad message")
        seen = [(e["source"], e["level"], e["message"]) for e in buffer.since(0)]
        assert ("core", "INFO", "Currently in state: searching") in seen
        assert ("uart", "INFO", '{"command":"stop"}') in seen
        assert ("sim", "WARNING", "Pico ignores bad message") in seen
        last = buffer.last_seq
        core.info("later")
        assert [e["message"] for e in buffer.since(last)] == ["later"]
    finally:
        logging.getLogger().removeHandler(buffer)
        logging.getLogger("dog_sim_host.uart").removeHandler(buffer)


def test_random_bone_lies_inside_the_search_area():
    import math
    import random

    from dog_sim_host.world import BONE_MARGIN, SEARCH_HALF_ANGLE

    world, rng = World(), random.Random(1)
    for _ in range(200):
        x, y, yaw = world.place_bone_randomly(rng)
        radius, off = math.hypot(x, y), math.atan2(y, -x)
        assert 1.5 + BONE_MARGIN <= radius <= 5.0 - BONE_MARGIN
        assert radius * math.sin(SEARCH_HALF_ANGLE - abs(off)) >= BONE_MARGIN
        assert 0 <= yaw < 360
    assert np.allclose(world.data.body("bone").xpos[:2], (x, y))


def test_light_reads_back_what_was_set():
    world = World()
    world.set_light(brightness=0.4, elevation=30, azimuth=200, ambient=0.2)
    assert world.light == {
        "brightness": 0.4,
        "elevation": 30.0,
        "azimuth": 200.0,
        "ambient": 0.2,
    }
    world.set_light(brightness=7, elevation=-10, azimuth=0, ambient=-1)  # clamped
    assert world.light["brightness"] == 1 and world.light["ambient"] == 0
    assert world.light["elevation"] == 5.0
