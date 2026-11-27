"""Render a YOLO training set of the bone from the simulator, labelled automatically.

Each image is the scene from a camera at the dog's eye height (Pi camera v2 field of view,
640 x 480) with the bone, floor, light and camera pose drawn at random. Labels come from
MuJoCo's segmentation render: the exact pixels of the bone, so boxes are tight and a bone
hidden behind a pylon is not labelled. About 15 % of images show no bone (negatives).

Classes are ``0 bone, 1 person, 2 shoe``, the shared detector's classes, so this set can be
merged with labelled real photos. The simulator's person is not realistic enough to learn
from, so it is moved out of view and the set has bone labels only.

    .venv-core/bin/python apps/sim-host/scripts/make_dataset.py              # 3000 images
    .venv-core/bin/python apps/sim-host/scripts/make_dataset.py -n 200 --out datasets/try
    .venv-core/bin/python apps/sim-host/scripts/make_dataset.py --floors photos/floors
    .venv-core/bin/python apps/sim-host/scripts/make_dataset.py --selfcheck

The first 16 images are also written with their boxes drawn into ``preview/``.
"""

import argparse
import math
from pathlib import Path

import cv2  # in the core environment
import mujoco
import numpy as np
from dog_sim_host.core_adapters import HEIGHT, WIDTH
from dog_sim_host.world import SCENE_PATH

REPO = Path(__file__).resolve().parents[3]
FOVY = 48.8  # degrees, the dog's camera in dog.xml
NAMES = {0: "bone", 1: "person", 2: "shoe"}
NEGATIVE_SHARE = 0.15
MIN_BONE_PIXELS = (
    60  # smaller slivers are ambiguous: resample instead of labelling them
)
FIELD_X, FIELD_Y = (-4.8, 1.5), (-1.5, 1.5)  # where the bone can lie: the taped field
FLOOR_HALF = 6.0  # m, the floor plane's half size in scene.xml
GENERATED_FLOORS = 16
PREVIEWS = 16


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("-n", "--count", type=int, default=3000)
    parser.add_argument("--out", type=Path, default=REPO / "datasets" / "sim")
    parser.add_argument(
        "--val", type=float, default=0.1, help="share for the val split"
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--floors",
        type=Path,
        help="folder of floor photos, each about 1 m wide, to use too",
    )
    parser.add_argument(
        "--selfcheck", action="store_true", help="check the labels and stop"
    )
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    photos = sorted(args.floors.glob("*.[jp][pn]g")) if args.floors else []
    scene = Scene(rng, photos)
    if args.selfcheck:
        selfcheck(scene)
        return

    for split in ("train", "val"):
        (args.out / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.out / "labels" / split).mkdir(parents=True, exist_ok=True)
    (args.out / "preview").mkdir(exist_ok=True)
    (args.out / "data.yaml").write_text(
        f"path: {args.out.resolve()}\ntrain: images/train\nval: images/val\nnames:\n"
        + "".join(f"  {i}: {name}\n" for i, name in NAMES.items())
    )

    positives = 0
    for index in range(args.count):
        image, box = scene.sample(negative=rng.random() < NEGATIVE_SHARE)
        image = camera_effects(image, rng)
        split = "val" if rng.random() < args.val else "train"
        name = f"sim_{index:06d}"
        quality = int(rng.integers(60, 96))
        cv2.imwrite(
            str(args.out / "images" / split / f"{name}.jpg"),
            image,
            [cv2.IMWRITE_JPEG_QUALITY, quality],
        )
        (args.out / "labels" / split / f"{name}.txt").write_text(
            yolo_line(0, box) if box else ""
        )
        positives += box is not None
        if index < PREVIEWS:
            if box:
                x1, y1, x2, y2 = box
                cv2.rectangle(image, (x1, y1), (x2, y2), (0, 220, 0), 1)
            cv2.imwrite(str(args.out / "preview" / f"{name}.jpg"), image)
        if (index + 1) % 250 == 0:
            print(f"{index + 1} / {args.count}")
    print(f"{args.count} images ({positives} with bone) in {args.out}")


class Scene:
    """The simulator's scene, changed for taking random pictures of the bone.

    A camera fixed to the world replaces the dog's head camera, the dog and the person
    stand far away, and the floor can switch between several textures.

    Args:
        rng: Random source for the floor textures.
        photos: Extra floor images, each taken to show about 1 m of floor.
    """

    def __init__(self, rng: np.random.Generator, photos: list[Path]) -> None:
        spec = mujoco.MjSpec.from_file(str(SCENE_PATH))
        spec.body("dog").pos = [
            50,
            0,
            0.27,
        ]  # out of the picture, not deleted: keeps the xml valid
        spec.body("person").pos = [60, 0, 0]
        spec.worldbody.add_camera(name="shot", fovy=FOVY)
        floors = [(image, metres) for image, metres in generated_floors(rng)]
        floors += [(cv2.imread(str(path)), 1.0) for path in photos]
        floors.append(
            (cv2.imread(str(SCENE_PATH.parent / "floor.png")), 1.0)
        )  # the field
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
            material.texrepeat = [
                1 / metres,
                1 / metres,
            ]  # with texuniform: repeats per metre
            material.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = f"floor_{index}"
        self.model = spec.compile()
        # The far-away dog makes the scene extent huge, and the near clip scales with it.
        self.model.vis.map.znear = 0.01 / self.model.stat.extent  # 1 cm
        self.data = mujoco.MjData(self.model)
        self.rng = rng
        self.floor_materials = [
            self.model.material(f"floor_{i}").id for i in range(len(floors))
        ]
        self.floor = self.model.geom("floor").id
        self.bone = self.model.geom("bone").id
        self.bone_material = self.model.material("bone").id
        self.bone_joint = self.model.joint("bone").qposadr[0]
        self.camera = self.model.camera("shot").id
        self.renderer = mujoco.Renderer(self.model, HEIGHT, WIDTH)
        self.options = mujoco.MjvOption()
        self.options.geomgroup[4] = 0  # the home marker is not on the real floor

    def sample(
        self, negative: bool
    ) -> tuple[np.ndarray, tuple[int, int, int, int] | None]:
        """A random picture (BGR) and the bone's pixel box, or None when no bone shows."""
        while True:
            self._randomize(negative)
            box, pixels = self._bone_box()
            if negative and pixels == 0:
                return self._render(), None
            if not negative and pixels >= MIN_BONE_PIXELS:
                return self._render(), box

    def place(self, bone_xy, bone_yaw, camera_xyz, yaw, pitch, roll=0.0) -> None:
        """Put the bone flat on the floor and the camera at a pose; angles in degrees."""
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

    def _randomize(self, negative: bool) -> None:
        rng, model = self.rng, self.model
        bone = np.array([rng.uniform(*FIELD_X), rng.uniform(*FIELD_Y)])
        # More close views than far ones: the dog gets close before it grabs the bone.
        camera = np.full(2, np.inf)
        while np.abs(camera).max() > FLOOR_HALF - 0.5:  # beyond the floor plane is void
            distance = math.exp(rng.uniform(math.log(0.3), math.log(3.0)))
            bearing = rng.uniform(0, 2 * math.pi)
            camera = bone + distance * np.array([math.cos(bearing), math.sin(bearing)])
        toward = math.degrees(math.atan2(*(bone - camera)[::-1]))
        # Off-centre by up to a bit more than half the 62 degree width: bones at the edge too.
        aim = toward + (rng.uniform(70, 290) if negative else rng.uniform(-36, 36))
        self.place(
            bone,
            rng.uniform(0, 360),
            (*camera, rng.uniform(0.18, 0.32)),  # the dog's eye height, head up or down
            aim,
            pitch=rng.uniform(8, 40),  # 20 degrees on the dog, the head nods
            roll=rng.normal(0, 3),
        )
        model.geom_matid[self.floor] = rng.choice(self.floor_materials)
        floor = model.geom_matid[self.floor]
        model.mat_rgba[floor] = (*np.full(3, rng.uniform(0.6, 1.0)), 1)
        model.mat_reflectance[floor] = rng.uniform(0, 0.3)
        model.mat_specular[floor] = rng.uniform(0, 0.6)
        model.mat_shininess[floor] = rng.uniform(0.1, 0.9)
        white = rng.uniform(0.82, 1.0)
        model.mat_rgba[self.bone_material] = (
            white,
            white * rng.uniform(0.95, 1),
            white * rng.uniform(0.85, 1),
            1,
        )
        down = np.array([rng.normal(0, 0.5), rng.normal(0, 0.5), -1])
        model.light_dir[0] = down / np.linalg.norm(down)
        model.light_diffuse[0] = rng.uniform(0.2, 0.8) * rng.uniform(0.9, 1.0, 3)
        model.vis.headlight.ambient = np.full(3, rng.uniform(0.25, 0.6))
        model.vis.headlight.diffuse = np.full(3, rng.uniform(0.2, 0.6))

    def _bone_box(self) -> tuple[tuple[int, int, int, int] | None, int]:
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

    def _render(self) -> np.ndarray:
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


def yolo_line(cls: int, box: tuple[int, int, int, int]) -> str:
    """One YOLO label line: class, then centre and size as fractions of the image."""
    x1, y1, x2, y2 = box
    return (
        f"{cls} {(x1 + x2) / 2 / WIDTH:.6f} {(y1 + y2) / 2 / HEIGHT:.6f} "
        f"{(x2 - x1) / WIDTH:.6f} {(y2 - y1) / HEIGHT:.6f}\n"
    )


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
    width = max(
        1, round(rng.uniform(0.002, 0.008) / tile_m * half / 2)
    )  # half a joint each side
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
    """What a real camera adds and the renderer does not: blur, motion blur, noise.

    Training adds colour, flips and scale itself (Ultralytics augmentation).
    """
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


def selfcheck(scene: Scene) -> None:
    """Bone 1 m straight ahead, across the view: the box must be centred and the right size."""
    height = 0.25
    pitch = math.degrees(math.atan2(height - 0.023, 1.0))
    scene.place((0.0, 0.0), 90, (-1.0, 0.0, height), 0, pitch)
    box, pixels = scene._bone_box()
    assert box is not None and pixels > MIN_BONE_PIXELS, "bone not seen"
    x1, y1, x2, y2 = box
    assert (
        abs((x1 + x2) / 2 - WIDTH / 2) < 10 and abs((y1 + y2) / 2 - HEIGHT / 2) < 15
    ), box
    # Pinhole: 21 cm at ~1.02 m with a 528 px focal length is ~108 px wide.
    focal = (HEIGHT / 2) / math.tan(math.radians(FOVY) / 2)
    expected = 0.21 * focal / math.hypot(1.0, height - 0.023)
    assert abs((x2 - x1) - expected) < 0.15 * expected, (x2 - x1, expected)
    line = yolo_line(0, box).split()
    assert line[0] == "0" and all(0 < float(v) < 1 for v in line[1:]), line
    scene.place((0.0, 0.0), 90, (-1.0, 0.0, height), 180, pitch)  # looking away
    assert scene._bone_box() == (None, 0), "bone seen behind the camera"
    print(f"selfcheck ok: box {box}, {x2 - x1} px wide, expected {expected:.0f}")


if __name__ == "__main__":
    main()
