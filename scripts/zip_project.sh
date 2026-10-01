#!/usr/bin/env bash
# إنشاء ملف مضغوط بالمشروع (يستبعد البيئات والمخابئ والأوزان)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/../pixel-studio-project.zip}"
cd "$ROOT/.."
rm -f "$OUT"
zip -rq "$OUT" "$(basename "$ROOT")" \
  -x "*/.venv/*" "*/__pycache__/*" "*/.pytest_cache/*" "*/node_modules/*" \
     "*/.cache/*" "*/models/*" "*/.git/*" "*.pyc" "*/.mypy_cache/*" "*/.ruff_cache/*" \
     "*/__test__/shots/*"
echo "✔ تم إنشاء: $OUT"
du -h "$OUT"
