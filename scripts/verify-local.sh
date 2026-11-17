#!/usr/bin/env bash
set -euo pipefail
python -m compileall -q src tests scripts/ci
python scripts/ci/check_docs.py
PYTHONPATH=src python -m pytest -q
