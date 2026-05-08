#!/usr/bin/env bash
set -euo pipefail

python3 -m compileall -q sample-services
python3 -c "import json, pathlib; [json.load(open(p)) for p in pathlib.Path('config').rglob('*.json')]"

if command -v docker >/dev/null 2>&1; then
  docker compose config --quiet
  echo "compose.yaml is valid"
else
  echo "docker is not installed or not on PATH; skipped docker compose validation"
fi

echo "static checks passed"
