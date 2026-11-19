"""Entry point: ``uv run dog-sim``. Runs the physics in real time and serves the viewer.

One asyncio loop does everything, in this order, every few milliseconds:

1. read UART commands from the virtual serial port and hand them to the Pico emulator
2. step the physics until simulation time catches up with the wall clock
3. send odometry back over UART every 50 ms
4. send a frame to every connected browser about 30 times a second
"""

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path

import mujoco
import numpy as np
from dog_protocol import PORT
from websockets.asyncio.server import ServerConnection, broadcast, serve

from dog_sim_host.core_adapters import CommandInbox, project
from dog_sim_host.core_runner import CoreRunner
from dog_sim_host.pico import PicoFirmware
from dog_sim_host.uart_link import DEFAULT_LINK, PtyLink
from dog_sim_host.world import DETECTABLE, World

log = logging.getLogger("dog_sim_host")

ODOMETRY_PERIOD = 0.05  # s, 20 Hz like the Pico
FRAME_PERIOD = 1 / 30  # s, to the browser
MAX_CATCH_UP = 0.1  # s of physics per loop turn at most; slower machines fall behind
GEOM_TYPES = {
    mujoco.mjtGeom.mjGEOM_PLANE: "plane",
    mujoco.mjtGeom.mjGEOM_SPHERE: "sphere",
    mujoco.mjtGeom.mjGEOM_CAPSULE: "capsule",
    mujoco.mjtGeom.mjGEOM_ELLIPSOID: "ellipsoid",
    mujoco.mjtGeom.mjGEOM_CYLINDER: "cylinder",
    mujoco.mjtGeom.mjGEOM_BOX: "box",
}


class Simulator:
    """Ties the world, the Pico emulator, the serial link and the browsers together.

    Args:
        link: Where to put the symlink to the virtual serial port.
        with_core: Also run the dog core (needs the dev-core branch).
    """

    def __init__(self, link: Path, with_core: bool) -> None:
        self.world = World()
        self.pico = PicoFirmware(self.world)
        self.uart = PtyLink(link)
        self.inbox = CommandInbox()
        self.core = CoreRunner(self.world, self.inbox, link) if with_core else None
        self.clients: set[ServerConnection] = set()

    async def run(self, port: int) -> None:
        """Serve browsers on `port` and simulate until cancelled."""
        if self.core:
            self.core.start()
        async with serve(self._serve_browser, "localhost", port):
            log.info("Viewer server on ws://localhost:%d", port)
            log.info("Core serial port: %s -> %s", self.uart.link, self.uart.port)
            await self._simulate()

    async def _simulate(self) -> None:
        start = time.monotonic() - self.world.time
        next_odometry = next_frame = 0.0
        while True:
            for message in self.uart.read_messages():
                self.pico.handle(message)
            behind = time.monotonic() - start - self.world.time
            if behind > MAX_CATCH_UP:
                start += behind - MAX_CATCH_UP  # drop time we cannot simulate
                behind = MAX_CATCH_UP
            self.world.advance(behind, self.pico.control)
            now = self.world.time
            if now < next_odometry - 1:  # the world was reset
                next_odometry = next_frame = 0.0
                start = time.monotonic()
            if now >= next_odometry:
                self.uart.send(self.pico.odometry())
                next_odometry = now + ODOMETRY_PERIOD
            if self.clients and now >= next_frame:
                broadcast(self.clients, json.dumps(self.frame()))
                next_frame = now + FRAME_PERIOD
            await asyncio.sleep(0.004)

    async def _serve_browser(self, connection: ServerConnection) -> None:
        self.clients.add(connection)
        try:
            await connection.send(json.dumps(self.scene()))
            async for raw in connection:
                try:
                    self.handle(json.loads(raw))
                except (ValueError, KeyError, TypeError) as error:
                    log.warning("Bad message from viewer %r: %s", raw, error)
        finally:
            self.clients.discard(connection)

    def handle(self, message: dict) -> None:
        """Act on one `dog_protocol.ClientMessage` from the viewer."""
        kind = message["type"]
        if kind == "pico":
            self.pico.handle(message["message"])
        elif kind == "voice":
            self.inbox.say(message["word"])
        elif kind == "gesture":
            self.inbox.gesture = message["gesture"]
        elif kind == "emergency_stop":
            self.pico.emergency_stop = bool(message["active"])
        elif kind == "place":
            self.world.place(
                message["object"], float(message["x"]), float(message["y"])
            )
        elif kind == "reset":
            self.pico.reset_with_world()
        else:
            raise ValueError(f"unknown type {kind!r}")

    def scene(self) -> dict:
        """The `dog_protocol.SceneMessage`: every shape the viewer should draw."""
        model = self.world.model
        geoms = []
        for i in range(model.ngeom):
            rgba = model.geom_rgba[i]
            geoms.append(
                {
                    "name": model.geom(i).name,
                    "body": model.body(model.geom_bodyid[i]).name,
                    "type": GEOM_TYPES.get(mujoco.mjtGeom(model.geom_type[i]), "box"),
                    "size": model.geom_size[i].round(4).tolist(),
                    "rgba": rgba.round(3).tolist(),
                }
            )
        return {"type": "scene", "geoms": geoms}

    def frame(self) -> dict:
        """The `dog_protocol.FrameMessage`: where everything is right now."""
        model, data = self.world.model, self.world.data
        poses = [
            _pose(data.geom_xpos[i], data.geom_xmat[i]) for i in range(model.ngeom)
        ]
        joints = []
        for i in range(model.nu):
            actuator = model.actuator(i)
            joint = model.joint(actuator.trnid[0])
            joints.append(
                {
                    "name": actuator.name,
                    "angle": round(float(data.qpos[joint.qposadr[0]]), 4),
                    "velocity": round(float(data.qvel[joint.dofadr[0]]), 3),
                    "target": round(float(data.ctrl[i]), 3),
                    "torque": round(float(data.actuator_force[i]), 4),
                    "limit": float(actuator.forcerange[1]),
                }
            )
        odometry = self.pico.odometry()
        snapshot = self.world.snapshot
        detections = {}
        for label, names in DETECTABLE.items():
            box = project(snapshot, names)
            if box:
                detections[label] = [round(value, 1) for value in box]
        return {
            "type": "frame",
            "time": round(self.world.time, 3),
            "poses": poses,
            "camera": _pose(data.cam("eye").xpos, data.cam("eye").xmat),
            "joints": joints,
            "sensors": {
                "left_distance_m": round(odometry["left_distance_m"], 4),
                "right_distance_m": round(odometry["right_distance_m"], 4),
                "heading_deg": round(odometry["heading_deg"], 2),
                "sonar_m": round(float(self.world.sensor("sonar")[0]), 3),
                "accel_z": round(float(self.world.sensor("imu_accel")[2]), 2),
                "x": round(float(data.body("dog").xpos[0]), 3),
                "y": round(float(data.body("dog").xpos[1]), 3),
            },
            "pico": self.pico.status,
            "core": {
                "attached": self.core is not None,
                "state": self.core.state if self.core else None,
                "error": self.core.error if self.core else None,
            },
            "detections": detections,
            "springs": self.springs(),
        }

    def springs(self) -> list[dict]:
        """Ends and pulling force of every tension spring (MuJoCo tendon)."""
        model, data = self.world.model, self.world.data
        ends = data.wrap_xpos.reshape(-1, 3)
        springs = []
        for i in range(model.ntendon):
            first = data.ten_wrapadr[i]
            last = first + data.ten_wrapnum[i] - 1
            stretch = data.ten_length[i] - model.tendon_lengthspring[i, 1]
            springs.append(
                {
                    "name": model.tendon(i).name,
                    "start": ends[first].round(4).tolist(),
                    "end": ends[last].round(4).tolist(),
                    "force": round(
                        float(model.tendon_stiffness[i] * max(stretch, 0)), 2
                    ),
                }
            )
        return springs


def _pose(pos: np.ndarray, mat: np.ndarray) -> list[float]:
    """Position and quaternion (w, x, y, z) as one rounded list."""
    quat = np.zeros(4)
    mujoco.mju_mat2Quat(quat, np.asarray(mat, dtype=float).ravel())
    return [round(float(v), 4) for v in (*pos, *quat)]


def main() -> None:
    """Parse the command line and run the simulator until Ctrl+C."""
    parser = argparse.ArgumentParser(description="Dog robot simulator (MuJoCo)")
    parser.add_argument("--port", type=int, default=PORT, help="WebSocket port")
    parser.add_argument(
        "--link", type=Path, default=DEFAULT_LINK, help="symlink to the serial port"
    )
    parser.add_argument(
        "--core", action="store_true", help="also run the dog core (dev-core branch)"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    simulator = Simulator(args.link, args.core)
    try:
        asyncio.run(simulator.run(args.port))
    except KeyboardInterrupt:
        pass
    finally:
        simulator.uart.close()
