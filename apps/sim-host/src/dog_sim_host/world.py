"""The simulated world: the MuJoCo scene with the dog, the bone and the person.

`World` owns the physics. Other modules only read from it (sensors, the viewer)
or set actuator targets on it (the Pico emulator). Positions are in metres in the
MuJoCo frame: x forwards from home, y to the left, z up.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import mujoco
import numpy as np

SCENE_PATH = Path(__file__).parent / "assets" / "scene.xml"

#: Geoms the simulated camera can detect, grouped by the label the detector reports.
DETECTABLE = {
    "bone": ("bone",),
    "person": ("person_leg_left", "person_leg_right", "person_torso", "person_head"),
    "shoe_left": ("shoe_left",),
    "shoe_right": ("shoe_right",),
}


@dataclass(frozen=True)
class GeomPose:
    """Where a geom is and how big its bounding box is.

    Attributes:
        pos: Centre in world coordinates, shape (3,).
        mat: Rotation from geom frame to world frame, shape (3, 3).
        half_size: Half extents of the geom's bounding box in its own frame, shape (3,).
    """

    pos: np.ndarray
    mat: np.ndarray
    half_size: np.ndarray


@dataclass(frozen=True)
class Snapshot:
    """A read-only copy of what the camera needs, safe to read from other threads.

    Attributes:
        time: Simulation time in seconds.
        camera_pos: Camera position in world coordinates, shape (3,).
        camera_mat: Camera axes as columns (x right, y up, looks along -z), shape (3, 3).
        geoms: Pose of every detectable geom, by geom name.
    """

    time: float
    camera_pos: np.ndarray
    camera_mat: np.ndarray
    geoms: dict[str, GeomPose]


class World:
    """Loads the scene and steps the physics.

    Args:
        scene_path: MJCF file to load. Defaults to the bundled scene.
    """

    def __init__(self, scene_path: Path = SCENE_PATH) -> None:
        self.model = mujoco.MjModel.from_xml_path(str(scene_path))
        self.data = mujoco.MjData(self.model)
        mujoco.mj_forward(self.model, self.data)
        #: Latest camera snapshot; replaced (never mutated) after each `advance`.
        self.snapshot = self._take_snapshot()

    @property
    def time(self) -> float:
        """Simulation time in seconds since the last reset."""
        return self.data.time

    def advance(self, seconds: float, control: Callable[[], None]) -> None:
        """Step the physics forward by about `seconds`.

        Args:
            seconds: How much simulated time to add. Zero or less does nothing.
            control: Called before every physics step to set `data.ctrl`.
        """
        steps = int(seconds / self.model.opt.timestep)
        for _ in range(steps):
            control()
            mujoco.mj_step(self.model, self.data)
        if steps:
            self.snapshot = self._take_snapshot()

    def reset(self) -> None:
        """Put everything back where the scene file has it."""
        mujoco.mj_resetData(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        self.snapshot = self._take_snapshot()

    def place(self, name: str, x: float, y: float, yaw: float = 0.0) -> None:
        """Move the bone or the person to a spot on the floor.

        Args:
            name: ``"bone"`` or ``"person"``.
            x: Target x in metres.
            y: Target y in metres.
            yaw: Bone only: turn in degrees, counter-clockwise from lying along x.

        Raises:
            ValueError: For any other name.
        """
        if name == "bone":
            joint = self.model.joint("bone")
            address = joint.qposadr[0]
            half = math.radians(yaw) / 2
            # Lying flat, turned about the vertical axis.
            pose = (x, y, 0.023, math.cos(half), 0, 0, math.sin(half))
            self.data.qpos[address : address + 7] = pose
            self.data.qvel[joint.dofadr[0] : joint.dofadr[0] + 6] = 0
        elif name == "person":
            mocap = self.model.body("person").mocapid[0]
            self.data.mocap_pos[mocap] = (x, y, 0)
        else:
            raise ValueError(f"Cannot place {name!r}; only 'bone' and 'person'")
        mujoco.mj_forward(self.model, self.data)
        self.snapshot = self._take_snapshot()

    def sensor(self, name: str) -> np.ndarray:
        """Current reading of a sensor declared in ``dog.xml``."""
        return self.data.sensor(name).data

    def heading_cw(self) -> float:
        """IMU yaw in clockwise degrees in [0, 360), as the Pico reports it."""
        w, x, y, z = self.sensor("imu_orientation")
        yaw_ccw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
        return -math.degrees(yaw_ccw) % 360

    def _take_snapshot(self) -> Snapshot:
        geoms = {}
        for names in DETECTABLE.values():
            for name in names:
                geom = self.data.geom(name)
                geoms[name] = GeomPose(
                    geom.xpos.copy(),
                    geom.xmat.reshape(3, 3).copy(),
                    _half_size(self.model, self.model.geom(name).id),
                )
        camera = self.data.cam("eye")
        return Snapshot(
            self.data.time,
            camera.xpos.copy(),
            camera.xmat.reshape(3, 3).copy(),
            geoms,
        )


def _half_size(model: mujoco.MjModel, geom_id: int) -> np.ndarray:
    """Half extents of a geom's bounding box in its own frame."""
    size = model.geom_size[geom_id]
    kind = mujoco.mjtGeom(model.geom_type[geom_id])
    if kind == mujoco.mjtGeom.mjGEOM_SPHERE:
        return np.full(3, size[0])
    if kind == mujoco.mjtGeom.mjGEOM_CAPSULE:
        return np.array([size[0], size[0], size[1] + size[0]])
    if kind == mujoco.mjtGeom.mjGEOM_CYLINDER:
        return np.array([size[0], size[0], size[1]])
    return size.copy()
