#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-/home/hamzah.al-omairi/miniconda3/envs/ortho-deepspeedv/bin/python}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

exec "${PYTHON_BIN}" -m uvicorn serving.app:app --host "${HOST}" --port "${PORT}"
