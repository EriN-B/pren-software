"""Build the shared detection-only YOLOE-26n NCNN model, once, off the robot.

Build requirements: ultralytics==8.4.197, ncnn, pnnx==20260526, and
git+https://github.com/ultralytics/CLIP.git@7ffa84b3bfa40c42ecc1c77147a855e69cb2dd40.
Ultralytics downloads mobileclip2_b.ts into the work directory on first use.
Only the three exported NCNN files are needed at runtime.
"""

import argparse
import hashlib
import os
import shutil
from pathlib import Path

from ultralytics import YOLOE
from ultralytics.utils import YAML

PROMPTS = ["bone", "dog bone", "dog chew bone", "chew toy", "person", "shoe"]
PACKAGE = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--work-dir", type=Path, default=PACKAGE.parents[1] / "models" / "export"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PACKAGE
        / "src/dog_perception/yoloe26n_model/dog-yoloe26n-detect-384x512_ncnn_model",
    )
    args = parser.parse_args()
    checkpoint, work, output = (
        args.checkpoint.resolve(),
        args.work_dir.resolve(),
        args.output.resolve(),
    )
    if not checkpoint.is_file():
        parser.error(f"Checkpoint does not exist: {checkpoint}")
    work.mkdir(parents=True, exist_ok=True)
    os.chdir(work)

    # Construct the detection architecture first: no segmentation head is retained.
    detector = YOLOE("yoloe-26n.yaml", task="detect").load(str(checkpoint))
    detector.set_classes(PROMPTS)
    assert type(detector.model.model[-1]).__name__ == "YOLOEDetect"
    weights = work / "dog-yoloe26n-detect-384x512.pt"
    detector.save(str(weights))
    detector = YOLOE(str(weights), task="detect")
    exported = Path(
        detector.export(format="ncnn", imgsz=(384, 512), batch=1, device="cpu")
    )
    metadata = YAML.load(exported / "metadata.yaml")
    assert metadata["task"] == "detect" and metadata["head"] == "YOLOEDetect"
    assert list(metadata["names"].values()) == PROMPTS
    metadata["source_checkpoint"] = checkpoint.name
    metadata["source_sha256"] = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    YAML.save(exported / "metadata.yaml", metadata)

    output.mkdir(parents=True, exist_ok=True)
    for name in ("model.ncnn.param", "model.ncnn.bin", "metadata.yaml"):
        shutil.copy2(exported / name, output / name)
    print(f"Shared detector exported to {output}")


if __name__ == "__main__":
    main()
