"""Make the floor texture (floor.png): the playing field's dark linoleum.

From a photo of the taped field (2026-11-20): dark warm-grey linoleum, no tiles, mottled,
full of fine light scratches, and glossy. The gloss (window reflections) comes from the
material in scene.xml, not from this image. The image covers 1 m; scene.xml repeats it.

    .venv-core/bin/python apps/sim-host/scripts/make_floor_texture.py
"""

from pathlib import Path

import cv2  # in the core environment
import numpy as np

OUT = Path(__file__).parents[1] / "src/dog_sim_host/assets/floor.png"
PIXELS = 1024  # 1 m
BASE_RGB = (58, 53, 45)  # the photo's floor where it reflects nothing
SCRATCHES = 900


def main() -> None:
    rng = np.random.default_rng(7)  # fixed, so the floor is the same every time
    image = np.empty((PIXELS, PIXELS, 3), np.float32)
    image[:] = BASE_RGB

    def noise(blur: float) -> np.ndarray:
        """Smooth random values around 0, tiling seamlessly (blurred with wrap-around)."""
        raw = rng.normal(0, 1, (PIXELS, PIXELS)).astype(np.float32)
        # Wrap the edges first, so the repeated image has no seams.
        pad = int(4 * blur) + 1
        wrapped = np.pad(raw, pad, mode="wrap")
        smooth = cv2.GaussianBlur(wrapped, (0, 0), blur)[pad:-pad, pad:-pad]
        return smooth / smooth.std()

    image *= (1 + 0.06 * noise(40) + 0.03 * noise(1.5))[..., None]  # mottling, grain
    scratches = np.zeros((PIXELS, PIXELS), np.float32)
    for _ in range(SCRATCHES):  # thin light scratches, mostly short, a few long
        start = rng.integers(0, PIXELS, 2)
        length = rng.exponential(40)
        angle = rng.uniform(0, np.pi)
        end = start + (length * np.array([np.cos(angle), np.sin(angle)])).astype(int)
        strength = rng.uniform(0.2, 1)
        cv2.line(
            scratches,
            tuple(map(int, start)),
            tuple(map(int, end)),
            strength,
            1,
            cv2.LINE_AA,
        )
    image += (scratches * 45)[..., None]
    cv2.imwrite(str(OUT), np.clip(image, 0, 255)[..., ::-1].astype(np.uint8))
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
