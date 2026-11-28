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
import numpy as np
from dog_sim_host.core_adapters import HEIGHT, WIDTH
from dog_sim_host.photos import FLOOR_HALF, FOVY, Scene, camera_effects

REPO = Path(__file__).resolve().parents[3]
NAMES = {0: "bone", 1: "person", 2: "shoe"}
NEGATIVE_SHARE = 0.15
MIN_BONE_PIXELS = (
    60  # smaller slivers are ambiguous: resample instead of labelling them
)
FIELD_X, FIELD_Y = (-4.8, 1.5), (-1.5, 1.5)  # where the bone can lie: the taped field
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
        image, box = sample(scene, rng, negative=rng.random() < NEGATIVE_SHARE)
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


def sample(
    scene: Scene, rng: np.random.Generator, negative: bool
) -> tuple[np.ndarray, tuple[int, int, int, int] | None]:
    """A random picture (BGR) and the bone's pixel box, or None when no bone shows."""
    while True:
        shoot(scene, rng, negative)
        box, pixels = scene.bone_box()
        if negative and pixels == 0:
            return scene.render(), None
        if not negative and pixels >= MIN_BONE_PIXELS:
            return scene.render(), box


def shoot(scene: Scene, rng: np.random.Generator, negative: bool) -> None:
    """Random bone, camera pose, floor and light, for training (wider than the robot)."""
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
    scene.place(
        bone,
        rng.uniform(0, 360),
        (*camera, rng.uniform(0.18, 0.32)),  # the dog's eye height, head up or down
        aim,
        pitch=rng.uniform(8, 40),  # 20 degrees on the dog, the head nods
        roll=rng.normal(0, 3),
    )
    scene.set_look(rng)


def yolo_line(cls: int, box: tuple[int, int, int, int]) -> str:
    """One YOLO label line: class, then centre and size as fractions of the image."""
    x1, y1, x2, y2 = box
    return (
        f"{cls} {(x1 + x2) / 2 / WIDTH:.6f} {(y1 + y2) / 2 / HEIGHT:.6f} "
        f"{(x2 - x1) / WIDTH:.6f} {(y2 - y1) / HEIGHT:.6f}\n"
    )


def selfcheck(scene: Scene) -> None:
    """Bone 1 m straight ahead, across the view: the box must be centred and the right size."""
    height = 0.25
    pitch = math.degrees(math.atan2(height - 0.023, 1.0))
    scene.place((0.0, 0.0), 90, (-1.0, 0.0, height), 0, pitch)
    box, pixels = scene.bone_box()
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
    assert scene.bone_box() == (None, 0), "bone seen behind the camera"
    print(f"selfcheck ok: box {box}, {x2 - x1} px wide, expected {expected:.0f}")


if __name__ == "__main__":
    main()
