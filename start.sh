#!/usr/bin/env bash
set -e
# On boot: generate the synthetic dataset + train models if artifacts are missing (< 1 min),
# then serve. Deterministic from the seed, so cold starts are reproducible.
if [ ! -f "$DATA_DIR/models/pd_model.pkl" ]; then
  echo "Bootstrapping synthetic data + models..."
  python scripts/train_all.py --seed 42 --data "$DATA_DIR"
fi
exec uvicorn backend.app:app --host 0.0.0.0 --port "${PORT:-8080}"
