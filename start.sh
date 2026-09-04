#!/usr/bin/env bash
set -e
# Artefacts are baked into the image at build time. This guard only fires if the image was built
# without them, in which case generation + training runs once (about 5 minutes) before serving.
if [ "${DATA_SOURCE:-synthetic}" = "synthetic" ] && [ ! -f "${DATA_DIR:-/app/data}/models/pd_model.pkl" ]; then
  echo "No baked artefacts found: bootstrapping synthetic data + models (deterministic, seed 42)..."
  python scripts/train_all.py --seed 42 --data "${DATA_DIR:-/app/data}"
fi
exec uvicorn backend.app:app --host 0.0.0.0 --port "${PORT:-8080}"
