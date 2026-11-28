"""Single pictures of the scene from any camera pose, with the bone's exact pixel box.

The simulator's scene, changed for taking pictures: a camera fixed to the world replaces
the dog's head camera, the dog stands far away, and the floor can switch between several
textures. Used for training images (``scripts/make_dataset.py``) and the detector test
bench (`dog_sim_host.bench`). Needs OpenCV (dev or bench dependencies).
"""

import math
from pathlib import Path

import cv2
import mujoco
import numpy as np

from dog_sim_host.core_adapters import HEIGHT, WIDTH
from dog_sim_host.world import SCENE_PATH

FOVY = 48.8  # degrees, the dog's camera in dog.xml
FLOOR_HALF = 6.0  # m, the floor plane's half size in scene.xml
GENERATED_FLOORS = 16
FAR_AWAY = (60.0, 0.0)  # where the person stands when it is not in the picture


class Scene:
    """The scene, ready for random pictures.

    Args:
        rng: Random source for the generated floor textures. The same seed gives the
            same floors, so seeded pictures are the same from run to run.
        photos: Extra floor images, each taken to show about 1 m of floor.
    """

    def __init__(self, rng: np.random.Generator, photos: list[Path] = ()) -> None:
        spec = mujoco.MjSpec.from_file(str(SCENE_PATH))
        # Out of the picture, not deleted: keeps the xml valid.
        spec.body("dog").pos = [50, 0, 0.27]
        spec.worldbody.add_camera(name="shot", fovy=FOVY)
        floors = list(generated_floors(rng))
        floors += [(cv2.imread(str(path)), 1.0) for path in photos]
        floors.append((cv2.imread(str(SCENE_PATH.parent / "floor.png")), 1.0))
        for index, (image, metres) in enumerate(floors):
            if image is None:
                raise ValueError(
                    f"cannot read floor photo {photos[index - GENERATED_FLOORS]}"
                )
            rgb = np.ascontiguousarray(image[..., ::-1])
            texture = spec.add_texture(
                name=f"floor_{index}", type=mujoco.mjtTexture.mjTEXTURE_2D
            )
            texture.width, texture.height, texture.nchannel = (
                rgb.shape[1],
                rgb.shape[0],
                3,
            )
            texture.data = rgb.tobytes()
            material = spec.add_material(name=f"floor_{index}", texuniform=True)
            # With texuniform: repeats per metre.
            material.texrepeat = [1 / metres, 1 / metres]
            material.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = f"floor_{index}"
        self.model = spec.compile()
        # The far-away dog makes the scene extent huge, and the near clip scales with it.
        self.model.vis.map.znear = 0.01 / self.model.stat.extent  # 1 cm
        self.data = mujoco.MjData(self.model)
        self.floor_materials = [
            self.model.material(f"floor_{i}").id for i in range(len(floors))
        ]
        #: Index into `floor_materials` of the field's real linoleum.
        self.field_floor = len(floors) - 1
        self.floor = self.model.geom("floor").id
        self.bone = self.model.geom("bone").id
        self.bone_material = self.model.material("bone").id
        self.bone_joint = self.model.joint("bone").qposadr[0]
        self.person = self.model.body("person").mocapid[0]
        self.camera = self.model.camera("shot").id
        self.renderer = mujoco.Renderer(self.model, HEIGHT, WIDTH)
        self.options = mujoco.MjvOption()
        self.options.geomgroup[4] = 0  # the home marker is not on the real floor
        self.place_person(*FAR_AWAY)

    def place(self, bone_xy, bone_yaw, camera_xyz, yaw, pitch, roll=0.0) -> None:
        """Put the bone flat on the floor and the camera at a pose; angles in degrees.

        ``yaw`` is the compass direction the camera looks along (counter-clockwise from
        +x), ``pitch`` how far it looks down.
        """
        half = math.radians(bone_yaw) / 2
        address = self.bone_joint
        self.data.qpos[address : address + 7] = (
            *bone_xy,
            0.023,
            math.cos(half),
            0,
            0,
            math.sin(half),
        )
        self.model.cam_pos[self.camera] = camera_xyz
        self.model.cam_quat[self.camera] = camera_quat(yaw, pitch, roll)
        mujoco.mj_forward(self.model, self.data)

    def place_person(self, x: float, y: float) -> None:
        """Stand the person (with its shoes) at a spot; `FAR_AWAY` hides it."""
        self.data.mocap_pos[self.person] = (x, y, 0)
        mujoco.mj_forward(self.model, self.data)

    def set_look(
        self,
        rng: np.random.Generator,
        floor: int | None = None,
        light: dict[str, float] | None = None,
    ) -> int:
        """Random floor colour and gloss, bone colour and light.

        Args:
            rng: Random source.
            floor: Index into `floor_materials`, or None for a random one.
            light: ``brightness``, ``elevation`` and ``azimuth`` (degrees) and
                ``ambient`` to use instead of a random light.

        Returns:
            The index of the floor used.
        """
        model = self.model
        if floor is None:
            floor = int(rng.integers(len(self.floor_materials)))
        material = self.floor_materials[floor]
        model.geom_matid[self.floor] = material
        model.mat_rgba[material] = (*np.full(3, rng.uniform(0.6, 1.0)), 1)
        model.mat_reflectance[material] = rng.uniform(0, 0.3)
        model.mat_specular[material] = rng.uniform(0, 0.6)
        model.mat_shininess[material] = rng.uniform(0.1, 0.9)
        white = rng.uniform(0.82, 1.0)
        model.mat_rgba[self.bone_material] = (
            white,
            white * rng.uniform(0.95, 1),
            white * rng.uniform(0.85, 1),
            1,
        )
        if light is None:
            down = np.array([rng.normal(0, 0.5), rng.normal(0, 0.5), -1])
            model.light_dir[0] = down / np.linalg.norm(down)
            model.light_diffuse[0] = rng.uniform(0.2, 0.8) * rng.uniform(0.9, 1.0, 3)
            model.vis.headlight.ambient = np.full(3, rng.uniform(0.25, 0.6))
        else:
            up, around = map(math.radians, (light["elevation"], light["azimuth"]))
            model.light_dir[0] = (
                -math.cos(up) * math.cos(around),
                -math.cos(up) * math.sin(around),
                -math.sin(up),
            )
            model.light_diffuse[0] = np.full(3, light["brightness"])
            model.vis.headlight.ambient = np.full(3, light["ambient"])
        model.vis.headlight.diffuse = np.full(3, rng.uniform(0.2, 0.6))
        # The renderer reads the light from data: without this it shows the last one.
        mujoco.mj_forward(model, self.data)
        return floor

    def bone_box(self) -> tuple[tuple[int, int, int, int] | None, int]:
        """The bone's visible pixel box (x1, y1, x2, y2) and its pixel count."""
        self.renderer.enable_segmentation_rendering()
        self.renderer.update_scene(
            self.data, camera=self.camera, scene_option=self.options
        )
        segment = self.renderer.render()
        self.renderer.disable_segmentation_rendering()
        mask = (segment[..., 0] == self.bone) & (
            segment[..., 1] == mujoco.mjtObj.mjOBJ_GEOM
        )
        return mask_box(mask), int(mask.sum())

    def render(self) -> np.ndarray:
        """The picture as OpenCV gives it: 640 x 480, BGR."""
        self.renderer.update_scene(
            self.data, camera=self.camera, scene_option=self.options
        )
        return self.renderer.render()[..., ::-1].copy()


def mask_box(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Pixel box (x1, y1, x2, y2), x2 and y2 exclusive, around the True pixels."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def camera_quat(yaw: float, pitch: float, roll: float) -> np.ndarray:
    """MuJoCo camera orientation looking along compass `yaw`, `pitch` degrees down.

    A MuJoCo camera looks along its -z axis with x to the image right and y up.
    """
    psi, theta, phi = map(math.radians, (yaw, pitch, roll))
    forward = np.array(
        [
            math.cos(psi) * math.cos(theta),
            math.sin(psi) * math.cos(theta),
            -math.sin(theta),
        ]
    )
    right = np.array([math.sin(psi), -math.cos(psi), 0.0])
    up = np.cross(right, forward)
    right, up = (
        math.cos(phi) * right + math.sin(phi) * up,
        math.cos(phi) * up - math.sin(phi) * right,
    )
    quat = np.zeros(4)
    mujoco.mju_mat2Quat(quat, np.column_stack([right, up, -forward]).flatten())
    return quat


def generated_floors(rng: np.random.Generator):
    """Random floors as (BGR image, metres it covers): half tiles with grout, half linoleum."""
    for index in range(GENERATED_FLOORS):
        yield tiles(rng) if index % 2 == 0 else linoleum(rng)


def tiles(rng: np.random.Generator, pixels: int = 512) -> tuple[np.ndarray, float]:
    """2 x 2 tiles with grout, seamless when repeated; tile size 15 to 60 cm."""
    tile_m = rng.uniform(0.15, 0.6)
    colour = rng.uniform(40, 235) * warm(rng)
    grout = rng.uniform(30, 235) * rng.uniform(0.9, 1.0, 3)
    image = np.empty((pixels, pixels, 3), np.float32)
    half = pixels // 2
    for row in range(2):
        for col in range(2):
            image[row * half : (row + 1) * half, col * half : (col + 1) * half] = (
                colour * rng.uniform(0.9, 1.1)
            )
    # Half a joint each side.
    width = max(1, round(rng.uniform(0.002, 0.008) / tile_m * half / 2))
    for start, stop in (
        (0, width),
        (half - width, half + width),
        (pixels - width, pixels),
    ):
        image[start:stop] = grout
        image[:, start:stop] = grout
    image *= 1 + 0.04 * rng.normal(0, 1, (pixels, pixels, 1))  # grain
    return np.clip(image, 0, 255).astype(np.uint8), 2 * tile_m


def linoleum(rng: np.random.Generator, pixels: int = 512) -> tuple[np.ndarray, float]:
    """Mottled plain floor covering 1 m, dark to light, seamless when repeated."""
    raw = rng.normal(0, 1, (pixels, pixels)).astype(np.float32)
    wrapped = np.pad(raw, 80, mode="wrap")
    mottle = cv2.GaussianBlur(wrapped, (0, 0), 20)[80:-80, 80:-80]
    mottle /= mottle.std()
    colour = rng.uniform(25, 200) * warm(rng)
    image = colour * (1 + 0.07 * mottle + 0.03 * raw)[..., None]
    return np.clip(image, 0, 255).astype(np.uint8), 1.0


def warm(rng: np.random.Generator) -> np.ndarray:
    """A BGR tint from neutral grey to terracotta; real floors are never purple or green."""
    green = rng.uniform(0.7, 1.0)
    return np.array([rng.uniform(0.55, 1.0) * green, green, 1.0])


def camera_effects(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """What a real camera adds and the renderer does not: blur, motion blur, noise."""
    if rng.random() < 0.5:
        image = cv2.GaussianBlur(image, (0, 0), rng.uniform(0.3, 1.3))
    if rng.random() < 0.2:
        length = int(rng.integers(3, 10))
        kernel = np.zeros((length, length), np.float32)
        kernel[length // 2] = 1 / length
        rotation = cv2.getRotationMatrix2D(
            (length / 2 - 0.5, length / 2 - 0.5), rng.uniform(0, 180), 1
        )
        image = cv2.filter2D(
            image, -1, cv2.warpAffine(kernel, rotation, (length, length))
        )
    noise = rng.normal(0, rng.uniform(0, 6), image.shape)
    return np.clip(image + noise, 0, 255).astype(np.uint8)
