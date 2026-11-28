# Training data for the bone detector

The core's detector (YOLOE-26n, text prompts `bone`, `person`, `shoe`) almost never finds the
bone on the real playing field in rendered images (see [Core integration](core-integration.md)).
To retrain it, the simulator renders labelled images, to be mixed with labelled real photos.

## Rendering a data set

```bash
.venv-core/bin/python apps/sim-host/scripts/make_dataset.py                 # 3000 images into datasets/sim
.venv-core/bin/python apps/sim-host/scripts/make_dataset.py -n 500 --out datasets/try --seed 1
.venv-core/bin/python apps/sim-host/scripts/make_dataset.py --floors photos/floors  # add real floor photos
.venv-core/bin/python apps/sim-host/scripts/make_dataset.py --selfcheck     # checks the labels
```

About 6 images per second on a MacBook. `datasets/` is not committed.

Each image is drawn at random:

| What | Range |
| --- | --- |
| Bone | anywhere on the taped field, any turn, white to cream |
| Camera | 0.3 to 3 m from the bone (more close views), 18 to 32 cm high, 8 to 40° down, bone anywhere in the 640 × 480 view, also cut off at the edge |
| Floor | 8 tile floors (15 to 60 cm tiles, any grout), 8 plain mottled floors, the field's linoleum (`floor.png`), and any photos from `--floors`; grey to terracotta, matte to glossy |
| Light | direction, strength and colour of the room light |
| Camera faults | blur, motion blur, sensor noise, JPEG quality 60 to 95 |
| No bone | 15 % of images, so the model learns that tape and pylons are not bones |

Labels come from MuJoCo's segmentation render, so a box holds exactly the bone's visible
pixels. Bones smaller than 60 pixels are not used, since a model cannot be fairly asked to see them.
The simulator's person is too simple to learn from, so it stands out of view: the set has
`bone` labels only. Real photos must bring `person` and `shoe`, or the model forgets them.

## Output

```
datasets/sim/
  data.yaml               classes 0 bone, 1 person, 2 shoe (the shared detector's)
  images/train, images/val    JPEG, 90 / 10 split
  labels/train, labels/val    YOLO format; empty file = no bone
  preview/                first 16 images with their box drawn in, for a quick look
```

To train on simulator and real images together, list both folders in one `data.yaml`
(`train: [/abs/datasets/sim/images/train, /abs/datasets/real/images/train]`). Judge every
model on held-out **real** frames only. A model trained on renders always scores well on renders.

## Real photos

Frames from videos of the real field are labelled in three steps:

```bash
# 1. Crop to the camera's 4:3, scale to 640 x 480, and pre-label bone, person and shoe with
#    YOLOE-26L (text prompts, full resolution, so far bones are found too).
.venv-core/bin/python apps/sim-host/scripts/prelabel_photos.py frames/*.jpg --out datasets/real
# 2. Check and fix the boxes in Label Studio (pip/uv tool "label-studio"), export YOLO.
# 3. Measure a detector on held-out real frames, the way the core runs it.
.venv-core/bin/python apps/sim-host/scripts/evaluate_detector.py datasets/real/images/val
.venv-core/bin/python apps/sim-host/scripts/evaluate_detector.py datasets/real/images/val \
    --model datasets/runs/sim-real/weights/best.pt
```

In the first set, 817 of the 921 final boxes are YOLOE's unchanged, 12 were moved and 92
drawn by hand. Split frames from video into train and val in blocks (e.g. every 5th block of 20
frames), not at random: neighbouring frames are near-copies.

First result (2026-11-28, 315 real + 909 rendered training frames, `yolo26n.pt`, 100 epochs,
76 held-out real frames from the same room): bone found in 73 of 73 frames (core's detector
before: 29), shoes 78 % (before: 0 %), persons 65 % (before: 56 %).

## Not covered

- Walls, furniture and people in the background: the scene has only a light grey sky.
- The bone always lies flat.
- Whether renders help on real images at all is still unknown. The real test set decides.
- The real test frames come from the same room as the training frames; a field elsewhere
  will score lower.
