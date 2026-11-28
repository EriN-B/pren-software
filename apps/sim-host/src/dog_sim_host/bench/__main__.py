"""Command line of the bench.

    python -m dog_sim_host.bench serve                      # dashboard, queue, GitHub watch
    python -m dog_sim_host.bench run --ref develop -n 200   # one run now, then a summary
    python -m dog_sim_host.bench run --ref develop --model best_ncnn_model

Settings come from ``BENCH_*`` environment variables (see `runner.Config`) and ``PORT``.
"""

import argparse
import logging
import os
import shutil
from pathlib import Path

from dog_sim_host.bench import runner, store


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(prog="python -m dog_sim_host.bench")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="dashboard, queue and GitHub watch")
    run = commands.add_parser("run", help="do one run now and print its summary")
    run.add_argument("--ref", default="develop", help="branch or commit of the core")
    run.add_argument("-n", "--trials", type=int, default=200)
    run.add_argument("--model", type=Path, help="model file or NCNN folder to test")
    args = parser.parse_args()
    config = runner.Config()

    if args.command == "serve":
        from dog_sim_host.bench import web

        web.serve(config, int(os.environ.get("PORT", "8000")))
        return

    db = store.connect(config.db_path)
    name = ""
    if args.model:
        name = args.model.name
        if args.model.is_dir() and not name.endswith("_ncnn_model"):
            name += "_ncnn_model"  # Ultralytics tells NCNN folders by this ending
        target = config.models / name
        if not target.exists():
            config.models.mkdir(parents=True, exist_ok=True)
            copy = shutil.copytree if args.model.is_dir() else shutil.copy
            copy(args.model, target)
    run_id = store.enqueue(db, "manual", args.ref, args.trials, model=name)
    runner.execute(
        db, config, db.execute("select * from runs where id = ?", (run_id,)).fetchone()
    )
    row = db.execute(
        "select status, error from runs where id = ?", (run_id,)
    ).fetchone()
    print(f"run {run_id}: {row['status']} {row['error']}".strip())
    print(store.summary(db, run_id))


if __name__ == "__main__":
    main()
