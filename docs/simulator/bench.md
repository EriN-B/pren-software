# Detector bench

Measures how well the core's bone detector sees the bone, on thousands of rendered single
pictures, and compares versions on the same pictures. It runs as one Docker container
(for example on a homelab with Coolify) and shows its results on a small web page.

## What a trial is

One picture from the dog's camera (40 cm high, 20° down, 640 × 480), drawn from a seed:

| Varies | Range |
| --- | --- |
| Distance camera → bone | 0.3 to 5 m |
| Angle | where the bone is seen, ±40° (the picture is ±31° wide, so partly cut off too) |
| Bone turn | any; reported as 0° (pointing at the camera) to 90° (lying across) |
| Floor | the field's linoleum in half the trials, else tiles or other linoleum |
| Light | strength, height and direction of the sun, ambient |
| Person with shoes | in 30 % of trials, somewhere ahead |
| Camera faults | in 50 %: blur, motion blur, noise, JPEG 60 to 95 |
| No bone in view | 10 % of trials, for false alarms |

A bone with fewer than 40 visible pixels (hidden behind a shoe, cut off at the edge) is not a
fair test: such a trial is drawn again. The core's own detector code (`object_model.py` from
`apps/robot/dog-perception` at the tested commit, with its thresholds) looks at the picture.
A **hit** is a box overlapping the true bone box by at least 0.5 (IoU). A **false alarm** is
a box in a picture without the bone. The same seed always gives the same picture, so two
runs with the same number of trials see exactly the same pictures.

## A run

A run is: a core commit (branch or hash), a model (the commit's own, or an uploaded one) and
a number of trials. Runs start

- **by hand** on the dashboard, or with `python -m dog_sim_host.bench run`,
- **on a new commit** of a watched branch (`dev-core`, `develop`): checked every 15 minutes
  with `git ls-remote`; a newer commit replaces a still queued run of an older one,
- **on a model upload**: tested on the last watched branch (`develop`).

The dashboard shows per run the hit rate as a map of distance × angle, hit rates by bone size,
turn, floor, light, person and camera faults, and every missed or falsely detected picture
(green: true box, red: detections). Two picked runs are compared side by side, with the
pictures only one of them gets right.

## Running locally

```bash
uv sync --all-packages --extra bench               # once: Ultralytics, NCNN, OpenCV
uv run python -m dog_sim_host.bench run --ref develop -n 200
uv run python -m dog_sim_host.bench run --ref develop -n 200 --model path/to/best_ncnn_model
BENCH_POLL=0 uv run python -m dog_sim_host.bench serve # dashboard on http://localhost:8000
```

Data (SQLite, models, pictures) goes to `./data`, or `BENCH_DATA`.

## Deploying on Coolify

1. **New resource** → *Public repository* → `https://github.com/EriN-B/pren-software`, the
   branch to deploy (e.g. `develop`).
2. **Build pack**: *Dockerfile*. Base directory `/`, Dockerfile location
   `/apps/sim-host/bench.Dockerfile`.
3. **Ports**: `8000`. No domain: reach it on the home network or VPN, at
   `http://<server>:8000` (map the port under *Ports Mappings*, e.g. `8000:8000`).
4. **Persistent storage**: a volume mounted at `/data`. Without it, results are lost on every
   redeploy.
5. **Environment variables** (all optional):

    | Variable | Default | Meaning |
    | --- | --- | --- |
    | `BENCH_BRANCHES` | `dev-core,develop` | branches watched for new commits; uploads test the last |
    | `BENCH_TRIALS` | `1000` | trials of automatic runs |
    | `BENCH_WORKERS` | `2` | pictures in parallel; about one CPU core and 1 GB RAM each |
    | `BENCH_POLL` | `900` | seconds between GitHub checks, `0` to switch off |
    | `BENCH_REPO` | the GitHub repo | where commits come from |

6. **Deploy**. The first build takes a few minutes (PyTorch CPU). On start the bench queues a
   run for the newest commit of each watched branch.

On 4 cores, a run of 1000 trials takes about 2 minutes. A run cut off by a restart goes on
where it stopped.

## Not covered

- The bone always lies flat; the dog stands still (no motion blur from driving).
- Only rendered pictures: how renders and real photos differ is measured with real frames
  (see [Training data](training-data.md)).
- The full search (driving, turning, returning) is a later step.
