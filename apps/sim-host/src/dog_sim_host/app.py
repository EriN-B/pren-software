"""Entry point: ``uv run dog-sim``. Runs the physics in real time and serves the viewer.

One asyncio loop does everything, in this order, every few milliseconds:

1. read UART commands from the virtual serial port and hand them to the Pico emulator
2. step the physics until simulation time catches up with the wall clock
3. send measurements (every 20 ms) and odometry (every 50 ms) back over UART
4. with the core: render the dog's camera for it 30 times a second
5. send a frame to every connected browser about 30 times a second, and with the core
   its camera image 15 times a second
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import mujoco
import numpy as np
from dog_protocol import PORT
from websockets.asyncio.server import ServerConnection, broadcast, serve
from websockets.exceptions import ConnectionClosed

from dog_sim_host.core_adapters import FRAME_RATE, HEIGHT, WIDTH, project
from dog_sim_host.core_runner import CoreRunner
from dog_sim_host.log_buffer import LogBuffer
from dog_sim_host.pico import PicoFirmware
from dog_sim_host.uart_link import DEFAULT_LINK, PtyLink
from dog_sim_host.world import DETECTABLE, World

log = logging.getLogger("dog_sim_host")
uart_log = logging.getLogger("dog_sim_host.uart")

ODOMETRY_PERIOD = 0.05  # s, 20 Hz like the Pico (old protocol)
MEASUREMENT_PERIOD = 0.02  # s, 50 Hz as proposed by the interface definition
FRAME_PERIOD = 1 / 30  # s, to the browser
# Images to the browser, as binary messages: one byte for which image, then a JPEG.
IMAGE_PERIOD = 1 / 15  # s, the dog's camera as the core gets it
WEBCAM_PERIOD = 1 / 10  # s, the webcam image the core's gesture model sees
WEBCAM_WIDTH = 480  # px, downscaled for the browser
IMAGE_DOG_CAMERA, IMAGE_WEBCAM = b"\x00", b"\x01"
MAX_CATCH_UP = 0.1  # s of physics per loop turn at most; slower machines fall behind
GEOM_TYPES = {
    mujoco.mjtGeom.mjGEOM_PLANE: "plane",
    mujoco.mjtGeom.mjGEOM_SPHERE: "sphere",
    mujoco.mjtGeom.mjGEOM_CAPSULE: "capsule",
    mujoco.mjtGeom.mjGEOM_ELLIPSOID: "ellipsoid",
    mujoco.mjtGeom.mjGEOM_CYLINDER: "cylinder",
    mujoco.mjtGeom.mjGEOM_BOX: "box",
    mujoco.mjtGeom.mjGEOM_MESH: "mesh",
}


class Simulator:
    """Ties the world, the Pico emulator, the serial link and the browsers together.

    Args:
        link: Where to put the symlink to the virtual serial port.
        with_core: Also run the dog core (needs ``scripts/core-env.sh``).
        webcam: Laptop camera index for the core's gestures, or None.
    """

    def __init__(self, link: Path, with_core: bool, webcam: int | None = 0) -> None:
        self.world = World()
        self.pico = PicoFirmware(self.world)
        self.uart = PtyLink(link)
        self.core = CoreRunner(link, webcam) if with_core else None
        # The core's camera image: the dog's view, rendered like the viewer's inset.
        self._renderer = (
            mujoco.Renderer(self.world.model, HEIGHT, WIDTH) if with_core else None
        )
        self._render_options = mujoco.MjvOption()
        # Sites and group-4 geoms are markers for the viewer, not part of the real world.
        self._render_options.sitegroup[:] = 0
        self._render_options.geomgroup[4] = 0
        self.clients: set[ServerConnection] = set()
        #: Every log line for the viewers' log dock.
        self.logs = LogBuffer()
        self.logs.attach()

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
        next_odometry = next_measurement = next_frame = next_camera = next_image = 0.0
        next_webcam = 0.0
        logs_sent = self.logs.last_seq
        while True:
            for message in self.uart.read_messages():
                uart_log.info("%s", json.dumps(message, separators=(",", ":")))
                try:
                    self.pico.handle(message)
                except (KeyError, ValueError, TypeError) as error:
                    # The core is untrusted input: a bad command must not stop the world.
                    log.warning("Pico ignores bad message %s: %r", message, error)
            behind = time.monotonic() - start - self.world.time
            if behind > MAX_CATCH_UP:
                start += behind - MAX_CATCH_UP  # drop time we cannot simulate
                behind = MAX_CATCH_UP
            self.world.advance(behind, self.pico.control)
            now = self.world.time
            if now < next_odometry - 1:  # the world was reset
                next_odometry = next_measurement = next_frame = next_camera = 0.0
                next_image = 0.0
                start = time.monotonic()
            if now >= next_odometry:
                self.uart.send(self.pico.odometry())
                # Keep the rate: schedule from the due time, not from when we got here.
                next_odometry = max(next_odometry + ODOMETRY_PERIOD, now)
            if now >= next_measurement:
                self.uart.send(self.pico.measurements())
                next_measurement = max(next_measurement + MEASUREMENT_PERIOD, now)
            if self.core and now >= next_camera:
                self.core.camera.rendered = self.render_camera()
                next_camera = max(next_camera + 1 / FRAME_RATE, now)
            if self.core and self.clients and now >= next_image:
                broadcast(self.clients, IMAGE_DOG_CAMERA + self.camera_jpeg())
                next_image = max(next_image + IMAGE_PERIOD, now)
            if self.core and self.clients and now >= next_webcam:
                webcam = self.webcam_jpeg()
                if webcam:
                    broadcast(self.clients, IMAGE_WEBCAM + webcam)
                next_webcam = max(next_webcam + WEBCAM_PERIOD, now)
            if self.clients and now >= next_frame:
                broadcast(self.clients, json.dumps(self.frame()))
                new_logs = self.logs.since(logs_sent)
                if new_logs:
                    message = {"type": "logs", "entries": new_logs}
                    broadcast(self.clients, json.dumps(message))
                    logs_sent = new_logs[-1]["seq"]
                next_frame = now + FRAME_PERIOD
            await asyncio.sleep(0.004)

    async def _serve_browser(self, connection: ServerConnection) -> None:
        self.clients.add(connection)
        try:
            await connection.send(json.dumps(self.scene()))
            backlog = self.logs.since(0)
            if backlog:  # what happened before this viewer connected
                await connection.send(json.dumps({"type": "logs", "entries": backlog}))
            async for raw in connection:
                try:
                    self.handle(json.loads(raw))
                except (ValueError, KeyError, TypeError) as error:
                    log.warning("Bad message from viewer %r: %s", raw, error)
        except ConnectionClosed:
            pass  # the viewer reloaded or closed mid-message: not an error
        finally:
            self.clients.discard(connection)

    def handle(self, message: dict) -> None:
        """Act on one `dog_protocol.ClientMessage` from the viewer."""
        kind = message["type"]
        if kind == "pico":
            self.pico.handle(message["message"])
        elif kind == "emergency_stop":
            self.pico.emergency_stop = bool(message["active"])
        elif kind == "place":
            x, y = float(message["x"]), float(message["y"])
            yaw = float(message.get("yaw", 0))  # optional: older viewers do not send it
            self.world.place(message["object"], x, y, yaw)
        elif kind == "reset" and self.core:
            self.restart()
        elif kind == "reset":
            self.pico.reset_with_world()
        else:
            raise ValueError(f"unknown type {kind!r}")

    def restart(self) -> None:
        """Start this whole process again: world, Pico and the core from scratch.

        The core cannot be reset from outside: its states loop in their own threads.
        A fresh process is the only clean start. Viewers reconnect by themselves.
        """
        log.info("Reset: restarting the simulator and the core")
        self.uart.close()
        os.execv(sys.executable, [sys.executable, *sys.argv])

    def render_camera(self) -> np.ndarray:
        """The dog's camera image as OpenCV gives it: 640 x 480, BGR."""
        self._renderer.update_scene(self.world.data, "eye", self._render_options)
        return self._renderer.render()[:, :, ::-1].copy()

    def camera_jpeg(self) -> bytes:
        """The image the core's detector gets right now, as JPEG for the viewer."""
        import cv2  # only installed in the core environment, like the core itself

        quality = [cv2.IMWRITE_JPEG_QUALITY, 75]
        _, jpeg = cv2.imencode(".jpg", self.core.camera.rendered, quality)
        return jpeg.tobytes()

    def webcam_jpeg(self) -> bytes | None:
        """The webcam image the core's gesture model gets right now, small, as JPEG."""
        webcam = self.core.camera.webcam if self.core else None
        frame = webcam.frame if webcam else None
        if frame is None:
            return None
        import cv2  # only installed in the core environment, like the core itself

        height = round(frame.shape[0] * WEBCAM_WIDTH / frame.shape[1])
        small = cv2.resize(frame, (WEBCAM_WIDTH, height), interpolation=cv2.INTER_AREA)
        _, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return jpeg.tobytes()

    def scene(self) -> dict:
        """The `dog_protocol.SceneMessage`: every shape the viewer should draw."""
        model = self.world.model
        geoms = []
        for i in range(model.ngeom):
            geom = {
                "name": model.geom(i).name,
                "body": model.body(model.geom_bodyid[i]).name,
                "type": GEOM_TYPES.get(mujoco.mjtGeom(model.geom_type[i]), "box"),
                "size": model.geom_size[i].round(4).tolist(),
                "rgba": _colour(model, i).round(3).tolist(),
            }
            if model.geom_dataid[i] >= 0 and geom["type"] == "mesh":
                geom["mesh"] = model.mesh(model.geom_dataid[i]).name
            geoms.append(geom)
        return {"type": "scene", "geoms": geoms, "meshes": self.meshes()}

    def meshes(self) -> dict[str, dict]:
        """Every mesh's triangles in its geom's frame (MuJoCo has re-centred them)."""
        model = self.world.model
        meshes = {}
        for i in range(model.nmesh):
            verts = slice(
                model.mesh_vertadr[i], model.mesh_vertadr[i] + model.mesh_vertnum[i]
            )
            faces = slice(
                model.mesh_faceadr[i], model.mesh_faceadr[i] + model.mesh_facenum[i]
            )
            meshes[model.mesh(i).name] = {
                "vertices": model.mesh_vert[verts].round(5).flatten().tolist(),
                "faces": model.mesh_face[faces].flatten().tolist(),
            }
        return meshes

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
            "core_detections": self.core.detections() if self.core else [],
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


def _colour(model: mujoco.MjModel, geom: int) -> np.ndarray:
    """A geom's colour as MuJoCo draws it: its material's, times its texture's average."""
    material = model.geom_matid[geom]
    if material < 0:
        return model.geom_rgba[geom]
    rgba = model.mat_rgba[material].copy()
    texture = model.mat_texid[material, mujoco.mjtTextureRole.mjTEXROLE_RGB]
    if texture >= 0:
        start = model.tex_adr[texture]
        pixels = model.tex_width[texture] * model.tex_height[texture]
        channels = model.tex_nchannel[texture]
        data = model.tex_data[start : start + pixels * channels].reshape(-1, channels)
        rgba[:3] *= data[:, :3].mean(axis=0) / 255
    return rgba


def main() -> None:
    """Parse the command line and run the simulator until Ctrl+C."""
    parser = argparse.ArgumentParser(description="Dog robot simulator (MuJoCo)")
    parser.add_argument("--port", type=int, default=PORT, help="WebSocket port")
    parser.add_argument(
        "--link", type=Path, default=DEFAULT_LINK, help="symlink to the serial port"
    )
    parser.add_argument(
        "--core",
        action="store_true",
        help="also run the dog core (scripts/core-env.sh)",
    )
    parser.add_argument(
        "--webcam", type=int, default=0, help="laptop camera for gestures, -1 for none"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    logging.getLogger("websockets").setLevel(logging.WARNING)  # one line per connection
    simulator = Simulator(
        args.link, args.core, None if args.webcam < 0 else args.webcam
    )
    try:
        asyncio.run(simulator.run(args.port))
    except KeyboardInterrupt:
        pass
    finally:
        simulator.uart.close()
