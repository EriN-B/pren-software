"""Make the floor texture (floor.png): the playing field's grey slate-look linoleum.

From photos of the field (2026-11-27): neutral dark-grey linoleum, no tiles, with a cloudy
slate pattern (lighter patches with crinkled vein edges), fine speckle, a few small light
pits, and many long, slightly curved light scratches that cross each other. The gloss
(window reflections) comes from the material in scene.xml, not from this image. The image
covers 1 m and tiles seamlessly; scene.xml repeats it.

    .venv-core/bin/python apps/sim-host/scripts/make_floor_texture.py
"""

from pathlib import Path

import cv2  # in the core environment
import numpy as np

OUT = Path(__file__).parents[1] / "src/dog_sim_host/assets/floor.png"
PIXELS = 1024  # 1 m, so 1 px = 1 mm
BASE_RGB = (
    52,
    53,
    55,
)  # neutral, slightly cool; renders like the photos under the scene light
LONG_SCRATCHES = 260  # 5..60 cm, curved, faint (chair and table legs)
SHORT_SCRATCHES = 700  # 1..5 cm
PITS = 120


def main() -> None:
    rng = np.random.default_rng(7)  # fixed, so the floor is the same every time

    def noise(blur: float) -> np.ndarray:
        """Smooth random values around 0, tiling seamlessly (blurred with wrap-around)."""
        raw = rng.normal(0, 1, (PIXELS, PIXELS)).astype(np.float32)
        pad = int(4 * blur) + 1
        wrapped = np.pad(raw, pad, mode="wrap")
        smooth = cv2.GaussianBlur(wrapped, (0, 0), blur)[pad:-pad, pad:-pad]
        return smooth / smooth.std()

    def veins(blur: float) -> np.ndarray:
        """Thin crinkled lines where smooth noise crosses zero (ridged noise), 0..1."""
        return np.exp(-((noise(blur) / 0.12) ** 2))

    # Slate: cloudy light patches, edged with fine veins at two scales, plus speckle.
    shade = (
        0.04 * noise(60)
        + 0.05 * noise(14)
        + 0.14
        * veins(22)
        * (noise(50) > 0)  # veins only in some patches, as in the photos
        + 0.08 * veins(8)
        + 0.05 * noise(0.8)
    )
    image = np.empty((PIXELS, PIXELS, 3), np.float32)
    image[:] = BASE_RGB
    image *= (1 + shade)[..., None]

    def draw(points: np.ndarray, value: float, layer: np.ndarray) -> None:
        """A polyline on the layer, drawn 9 times shifted by +-1 image so it tiles."""
        for dx in (-PIXELS, 0, PIXELS):
            for dy in (-PIXELS, 0, PIXELS):
                shifted = (points + (dx, dy)).astype(np.int32)
                cv2.polylines(layer, [shifted], False, value, 1, cv2.LINE_AA)

    marks = np.zeros((PIXELS, PIXELS), np.float32)

    def scratch(length: float, strength: float, bend: float) -> None:
        """A scratch whose direction drifts slowly, so long ones curve gently."""
        steps = max(2, int(length / 8))
        angle = rng.uniform(0, np.pi)
        turn = np.cumsum(rng.normal(0, bend, steps))
        directions = np.stack([np.cos(angle + turn), np.sin(angle + turn)], axis=1)
        points = rng.uniform(0, PIXELS, 2) + np.cumsum(
            directions * length / steps, axis=0
        )
        draw(points, strength, marks)

    for _ in range(LONG_SCRATCHES):
        scratch(rng.uniform(50, 600), rng.uniform(0.15, 0.5), 0.015)
    for _ in range(SHORT_SCRATCHES):
        scratch(rng.uniform(10, 50), rng.uniform(0.3, 1.0), 0.05)
    for _ in range(PITS):  # small light pits, 1..3 mm
        x, y = rng.integers(0, PIXELS, 2)
        cv2.circle(
            marks, (int(x), int(y)), int(rng.integers(1, 3)), rng.uniform(0.3, 0.7), -1
        )

    image += (np.minimum(marks, 1) * 38)[..., None]
    cv2.imwrite(str(OUT), np.clip(image, 0, 255)[..., ::-1].astype(np.uint8))
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
