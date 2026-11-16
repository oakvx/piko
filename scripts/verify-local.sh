#!/usr/bin/env bash
set -euo pipefail
python -m compileall -q src tests
PYTHONPATH=src python -m pytest -q
