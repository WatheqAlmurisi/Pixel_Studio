#!/usr/bin/env bash
# تهيئة المشروع مرة واحدة (بيئة معزولة + اعتماديات)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt
echo "✔ اكتملت التهيئة. شغّل المشروع بـ: bash scripts/run.sh"
